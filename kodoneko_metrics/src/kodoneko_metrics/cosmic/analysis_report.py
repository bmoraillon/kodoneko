"""Analyse COSMIC enrichie : regroupement par functional process, inférence
des objets d'intérêt / data groups, et intervalle de confiance.

Ce module transforme la sortie brute du CosmicAnalyzer (une liste plate de
CosmicMovement) en une vue structurée façon manuel COSMIC, avec :

1. Regroupement des mouvements par functional process (un Entry ouvre un FP).
2. Inférence des objets d'intérêt et data groups (heuristique, marquée estimée).
3. Application de la frequency rule sur les Exits d'erreur/confirmation
   (Guidance Rules 16-19a : 1 seul Exit erreur/confirmation par FP), pour
   produire une borne "COSMIC strict" en plus de la borne brute.
4. Calcul d'un intervalle de confiance A+B :
   - A (bornes de jugement) : borne basse = comptage après fusion des Exits
     erreur/confirmation et absorption des Reads de rechargement ; borne haute
     = comptage brut (chaque mouvement détecté = 1 CFP).
   - B (confiance détecteurs) : les mouvements 'high' forment le plancher
     certain, les 'medium'/'low' élargissent l'incertitude.

IMPORTANT : ce module ne PROMET PAS un comptage COSMIC certifié. L'analyse
statique ne peut pas déterminer de façon fiable les FUR, les objets d'intérêt
et les fréquences d'occurrence — qui exigent un jugement humain sur les
requirements. Les valeurs OOI/data group sont des ESTIMATIONS et sont marquées
comme telles. La valeur produite est un estimateur avec intervalle, pas une
mesure exacte.

Références : COSMIC Measurement Manual v5.0 Part 2 (Guidelines), case studies
C-REG v2.0.1 et Web Advice Module v1.1.1.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field

from .models import CosmicMovement, CosmicFileReport


# Détecteurs d'Exit qui correspondent à des messages d'erreur/confirmation.
# Ces Exits sont sujets à la frequency rule : tous fusionnés en 1 par FP.
# (Guidance Rules 16-19a du manuel v5.0.)
_ERROR_CONFIRMATION_DETECTORS = frozenset({
    # Python
    "http_raise_HTTPException",
    # JS/TS
    "nestjs_throw_http_exception",
    # Java
    "spring_throw_responsestatus",
    "spring_throw_http",
})

# Mots-clés dans le détecteur indiquant un Exit "message" (erreur/confirmation)
# plutôt qu'un Exit "données". Heuristique pour le code MVC (returns multiples).
_MESSAGE_EXIT_HINTS = ("raise", "throw", "error", "abort", "reject")

# Identifiant PascalCase = candidat objet d'intérêt (compilé une fois).
_PASCAL_RE = re.compile(r"\b([A-Z][a-zA-Z0-9]+)\b")

# Mots techniques à exclure de l'inférence d'objet d'intérêt : types,
# exceptions, primitives, annotations — jamais des objets métier.
_OOI_NOISE = frozenset({
    "Optional", "List", "Page", "Pageable", "PageRequest", "ResponseEntity",
    "String", "Integer", "Boolean", "Long", "Double", "Float", "Object",
    "Model", "ModelAndView", "BindingResult", "RedirectAttributes",
    "True", "False", "None", "Map", "Set", "Collection",
    "HTTPException", "ResponseStatusException", "IllegalArgumentException",
    "Exception", "RuntimeException", "Error", "ValidationError",
    "GetMapping", "PostMapping", "PutMapping", "DeleteMapping",
})

# Suffixe de data group par type de mouvement.
_DATA_GROUP_SUFFIX = {
    "entry": "details",      # données entrantes de l'objet
    "exit": "details",       # données sortantes
    "read": "record",        # lecture persistance
    "write": "record",       # écriture persistance
}

# Suffixes de fichiers/classes à retirer pour déduire l'objet métier
# (OwnerController.java → Owner, owner_service.py → owner).
_CLASS_NAME_SUFFIXES = (
    "Controller", "RestController", "Resource", "Service", "ServiceImpl",
    "Repository", "Handler", "Router", "View", "ViewSet", "Api", "Endpoint",
)


def _ooi_from_filename(path: str) -> str:
    """Déduit un objet d'intérêt candidat à partir du nom de fichier/classe.

    OwnerController.java → "Owner" ; owner_routes.py → "Owner" ;
    pet_service.py → "Pet". Fallback fiable quand le code ne porte pas
    explicitement le type.
    """
    import os
    stem = os.path.basename(path or "")
    # Retirer l'extension
    stem = stem.rsplit(".", 1)[0]
    if not stem:
        return ""
    # snake_case ou kebab → prendre le 1er segment significatif
    if "_" in stem or "-" in stem:
        import re as _re
        parts = [p for p in _re.split(r"[_-]", stem) if p]
        # retirer un segment de rôle final (routes, service, views...)
        role_words = {"routes", "route", "service", "services", "views", "view",
                      "controller", "api", "handler", "repository", "repo",
                      "models", "model", "endpoints", "endpoint"}
        parts = [p for p in parts if p.lower() not in role_words]
        if parts:
            return parts[0].capitalize()
        return ""
    # PascalCase : retirer un suffixe de rôle connu
    for suffix in _CLASS_NAME_SUFFIXES:
        if stem.endswith(suffix) and len(stem) > len(suffix):
            return stem[: -len(suffix)]
    # Sinon, garder tel quel s'il est capitalisé
    return stem if stem[:1].isupper() else ""


def _ooi_from_excerpt(excerpt: str) -> str:
    """Extrait un objet d'intérêt (PascalCase non technique) d'un extrait."""
    for c in _PASCAL_RE.findall(excerpt or ""):
        if (c not in _OOI_NOISE
                and not c.endswith("Exception")
                and not c.endswith("Error")
                and not c.endswith("Dto")
                and not c.endswith("DTO")):
            return c
    return ""


# Extraction du nom de la fonction/méthode déclenchant un processus.
# Python:  "@app.post def process_creation(...)"  -> process_creation
# JS/TS:   "function createUser(...)" / "createUser(...)"  -> createUser
# Java:    "public ResponseEntity addOwner(...)"  -> addOwner
_FUNC_NAME_RES = (
    re.compile(r"\bdef\s+([A-Za-z_]\w*)"),                  # Python
    re.compile(r"\bfunction\s+([A-Za-z_$][\w$]*)"),         # JS function
    re.compile(r"\b([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{"),   # JS method body
    re.compile(r"\b([a-z][A-Za-z0-9_]*)\s*\("),             # fallback camelCase call
)


def _function_name_from_movement(m) -> str:
    """Extrait le nom de la fonction/méthode d'un mouvement Entry, si présent
    dans l'extrait de code. Chaîne vide sinon."""
    excerpt = m.code_excerpt or ""
    for rx in _FUNC_NAME_RES:
        mt = rx.search(excerpt)
        if mt:
            name = mt.group(1)
            # Écarter les mots-clés évidents
            if name not in {"if", "for", "while", "return", "def", "function"}:
                return name
    return ""


def _is_error_confirmation(m: CosmicMovement) -> bool:
    """True si ce mouvement est un Exit de message erreur/confirmation.

    Fonction module (et non méthode) car utilisée à la fois par
    FunctionalProcessView et par l'inférence des data groups.
    """
    if m.detector in _ERROR_CONFIRMATION_DETECTORS:
        return True
    d = m.detector.lower()
    return any(h in d for h in _MESSAGE_EXIT_HINTS)


@dataclass
class FunctionalProcessView:
    """Vue d'un functional process : ses mouvements et ses sous-totaux."""
    name: str
    movements: list[CosmicMovement] = field(default_factory=list)
    # Métadonnées descriptives (remplies par group_by_functional_process)
    function_name: str = ""   # nom de la fonction/méthode, ex: "processCreationForm"
    start_line: int = 0       # ligne du mouvement Entry déclencheur
    detector: str = ""        # pattern ayant détecté l'Entry, ex: "spring_post_mapping"

    @property
    def raw_cfp(self) -> int:
        """CFP brut : chaque mouvement détecté compte 1 (borne haute)."""
        return len(self.movements)

    @property
    def min_cfp(self) -> int:
        """CFP sous l'hypothèse de fusion MAXIMALE (borne basse de l'intervalle).

        Hypothèse la plus COSMIC-strict possible : TOUS les Exits d'un même
        functional process fusionnent en 1 seul (cas où tous les returns sont
        des messages erreur/confirmation, sans sortie de données distincte —
        typique d'un POST de modification : re-render erreur + redirect mismatch
        + redirect succès = 1 seul Exit message).

        C'est la borne basse honnête : elle représente le scénario où le
        comptage COSMIC fusionne le plus. La vérité se situe entre min_cfp
        (fusion maximale) et raw_cfp (aucune fusion).
        """
        entries = [m for m in self.movements if m.type == "entry"]
        reads = [m for m in self.movements if m.type == "read"]
        writes = [m for m in self.movements if m.type == "write"]
        exits = [m for m in self.movements if m.type == "exit"]
        # Tous les Exits du FP fusionnent en 1 (s'il y en a au moins un)
        exit_count = 1 if exits else 0
        return len(entries) + len(reads) + len(writes) + exit_count

    @property
    def strict_cfp(self) -> int:
        """CFP après application de la frequency rule (valeur centrale, la
        meilleure estimation COSMIC).

        Règles de fusion (Guidance Rules 16-19a) :
        1. Tous les Exits explicitement erreur/confirmation (raise/throw)
           fusionnent en 1 seul par FP.
        2. Cas L10 (returns multiples) : quand un FP a PLUSIEURS Exits
           génériques (returns de vue / redirects), l'analyse statique ne peut
           pas distinguer les sorties de données des messages. Hypothèse
           COSMIC la plus plausible : 1 Exit de données (l'objet d'intérêt
           principal) + 1 Exit message erreur/confirmation pour le reste.
           Cette fusion s'applique que le FP ait une écriture ou non (un GET
           de recherche avec re-render de formulaire + liste + "not found"
           suit la même logique qu'un POST).

        C'est la valeur centrale ; min_cfp est la borne basse (fusion max),
        raw_cfp la borne haute (aucune fusion).
        """
        entries = [m for m in self.movements if m.type == "entry"]
        reads = [m for m in self.movements if m.type == "read"]
        writes = [m for m in self.movements if m.type == "write"]
        exits = [m for m in self.movements if m.type == "exit"]

        explicit_err = [m for m in exits if self._is_error_confirmation(m)]
        generic_exits = [m for m in exits if not self._is_error_confirmation(m)]

        has_message_exit = len(explicit_err) > 0

        if len(generic_exits) > 1:
            # Returns multiples : 1 Exit données + le reste fusionné en message.
            # (Indépendant de la présence d'un Write : un GET recherche avec
            #  plusieurs returns suit la même règle qu'un POST.)
            exit_count = 1
            has_message_exit = True
        else:
            # 0 ou 1 Exit générique : pas de fusion à faire
            exit_count = len(generic_exits)

        if has_message_exit:
            exit_count += 1

        return len(entries) + len(reads) + len(writes) + exit_count

    @property
    def has_fusion_uncertainty(self) -> bool:
        """True si ce FP a une incertitude de fusion (écart entre la borne
        basse de fusion maximale et le comptage brut)."""
        return self.min_cfp != self.raw_cfp

    @property
    def high_confidence_cfp(self) -> int:
        """Plancher B : seuls les mouvements 'high' sont certains."""
        return sum(1 for m in self.movements if m.confidence == "high")

    @staticmethod
    def _is_error_confirmation(m: CosmicMovement) -> bool:
        # Conservé pour rétrocompat ; délègue à la fonction module.
        return _is_error_confirmation(m)

    def by_type(self) -> dict:
        result = {"entry": 0, "read": 0, "write": 0, "exit": 0}
        for m in self.movements:
            result[m.type] += 1
        return result


@dataclass
class ConfidenceInterval:
    """Intervalle de confiance A+B sur le comptage CFP."""
    low: int       # borne basse : strict (frequency rule) ∩ haute confiance
    central: int   # valeur centrale : strict CFP
    high: int      # borne haute : comptage brut
    high_confidence_floor: int  # plancher des seuls détecteurs 'high'

    def to_dict(self) -> dict:
        return {
            "low": self.low,
            "central": self.central,
            "high": self.high,
            "high_confidence_floor": self.high_confidence_floor,
            "label": self.label(),
        }

    def label(self) -> str:
        """Représentation lisible : 'central CFP [low–high]'."""
        if self.low == self.high:
            return f"{self.central} CFP"
        return f"{self.central} CFP [{self.low}–{self.high}]"


# ===========================================================================
# Inférence des objets d'intérêt et data groups (heuristique, estimée)
# ===========================================================================

def _infer_object_of_interest(m: CosmicMovement, fallback: str = "") -> str:
    """Infère l'objet d'intérêt d'un mouvement.

    Stratégie à deux niveaux :
    1. Signal propre au mouvement : un nom PascalCase dans l'extrait
       (ex: `session.get(Owner, id)` → "Owner").
    2. Fallback : l'OOI inféré au niveau du functional process (issu du nom
       de fichier ou d'un autre mouvement du même FP).

    Un Exit d'erreur/confirmation n'a jamais d'objet métier (c'est un message).
    """
    if m.type == "exit" and _is_error_confirmation(m):
        return ""
    own = _ooi_from_excerpt(m.code_excerpt or "")
    return own or fallback


def _infer_fp_object_of_interest(movements, file_path: str) -> str:
    """Infère l'objet d'intérêt dominant d'un functional process.

    Cherche le PascalCase le plus fréquent parmi les extraits des mouvements ;
    à défaut, déduit du nom de fichier. C'est cet OOI qui sert de fallback
    pour les mouvements sans signal propre (ex: `session.add(owner)`).
    """
    from collections import Counter
    counter: Counter = Counter()
    for m in movements:
        c = _ooi_from_excerpt(m.code_excerpt or "")
        if c:
            counter[c] += 1
    if counter:
        return counter.most_common(1)[0][0]
    return _ooi_from_filename(file_path)


def _infer_data_group(m: CosmicMovement, ooi: str) -> str:
    """Infère un nom de data group à partir du type de mouvement et de l'OOI."""
    if not ooi:
        # Exit message d'erreur/confirmation
        if m.type == "exit" and _is_error_confirmation(m):
            return "Error/confirmation messages"
        return ""
    return f"{ooi} {_DATA_GROUP_SUFFIX.get(m.type, 'data')}"


# ===========================================================================
# Construction de la vue enrichie
# ===========================================================================

def group_by_functional_process(
    movements: list[CosmicMovement],
) -> list[FunctionalProcessView]:
    """Regroupe les mouvements en functional processes.

    Heuristique : chaque Entry ouvre un nouveau FP ; les mouvements suivants
    (jusqu'au prochain Entry) lui sont rattachés.

    Cas des mouvements orphelins (avant le premier Entry) : typiquement un
    Read de méthode partagée (`@ModelAttribute` en Spring, dépendance FastAPI).
    Plutôt que d'en faire un "FP préambule" fantôme — qui pollue le comptage
    par functional process — on les met EN ATTENTE et on les rattache au
    premier FP réel rencontré. Si aucun Entry n'existe dans tout le fichier
    (code utilitaire pur), ils forment alors un seul FP "hors endpoint".
    """
    fps: list[FunctionalProcessView] = []
    current: FunctionalProcessView | None = None
    pending: list[CosmicMovement] = []  # orphelins avant le 1er Entry
    counter = 0

    for m in sorted(movements, key=lambda x: (x.line, 0 if x.type == "entry" else 1)):
        if m.type == "entry":
            counter += 1
            fn = _function_name_from_movement(m)
            if fn:
                name = f"FP{counter} : {fn}()"
            else:
                name = f"FP{counter} (ligne {m.line})"
            current = FunctionalProcessView(
                name=name,
                function_name=fn,
                start_line=m.line,
                detector=m.detector,
            )
            # Rattacher les orphelins en attente au premier FP réel
            if pending:
                current.movements.extend(pending)
                pending = []
            fps.append(current)
        if current is None:
            # Pas encore d'Entry : mettre en attente (ne PAS créer de FP fantôme)
            pending.append(m)
            continue
        current.movements.append(m)

    # Aucun Entry de tout le fichier : les orphelins forment un FP hors-endpoint
    if pending:
        fp = FunctionalProcessView(name="FP (hors endpoint)")
        fp.movements = pending
        fps.append(fp)

    return fps


def enrich_movements(movements: list[CosmicMovement]) -> list[CosmicMovement]:
    """Enrichit chaque mouvement avec OOI et data group inférés.

    CosmicMovement étant frozen, retourne de NOUVELLES instances enrichies
    (ne mute pas les originaux).
    """
    enriched = []
    for m in movements:
        ooi = _infer_object_of_interest(m)
        dg = _infer_data_group(m, ooi)
        enriched.append(dataclasses.replace(
            m, object_of_interest=ooi, data_group=dg, inferred=True,
        ))
    return enriched


def compute_interval(fps: list[FunctionalProcessView]) -> ConfidenceInterval:
    """Calcule l'intervalle de confiance agrégé sur tous les FP.

    L'incertitude a deux sources, et l'intervalle reflète la PRINCIPALE
    (le jugement de fusion COSMIC), tout en exposant la seconde séparément :

    - **high** (borne haute) : comptage brut, aucune fusion (chaque mouvement
      détecté = 1 CFP). C'est ce que voit l'analyse statique naïve.
    - **central** : comptage strict, frequency rule appliquée (fusion des
      messages erreur/confirmation). Meilleure estimation COSMIC.
    - **low** (borne basse) : le comptage strict est déjà l'hypothèse de
      fusion maximale plausible — c'est donc la borne basse côté jugement.
      On la croise avec le plancher haute-confiance UNIQUEMENT s'il est
      supérieur (cas où peu de medium) ; on ne descend PAS au plancher HC
      brut car supposer que tous les Exits 'medium' sont faux est irréaliste.
    - **high_confidence_floor** : exposé séparément comme garde-fou détection
      (minimum si l'on ne gardait que les détecteurs 'high').

    Résultat : un intervalle [strict, raw] resserré autour de la réalité
    COSMIC, là où l'ancienne version descendait au plancher HC (irréaliste).
    """
    raw = sum(fp.raw_cfp for fp in fps)
    strict = sum(fp.strict_cfp for fp in fps)
    minimal = sum(fp.min_cfp for fp in fps)
    hc_floor = sum(fp.high_confidence_cfp for fp in fps)

    # Borne basse = fusion maximale (tous les Exits d'un FP en 1). C'est
    # l'hypothèse COSMIC-strict la plus basse plausible ; elle garantit que
    # l'intervalle encadre la vérité par le bas.
    low = minimal
    central = strict
    return ConfidenceInterval(
        low=low,
        central=central,
        high=raw,
        high_confidence_floor=hc_floor,
    )


@dataclass
class EnrichedFileAnalysis:
    """Analyse COSMIC enrichie complète d'un fichier."""
    path: str
    language: str
    functional_processes: list[FunctionalProcessView]
    interval: ConfidenceInterval

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "language": self.language,
            "interval": self.interval.to_dict(),
            "functional_processes": [
                {
                    "name": fp.name,
                    "raw_cfp": fp.raw_cfp,
                    "strict_cfp": fp.strict_cfp,
                    "by_type": fp.by_type(),
                    "movements": [m.to_dict() for m in fp.movements],
                }
                for fp in self.functional_processes
            ],
        }


def analyze_enriched(file_report: CosmicFileReport) -> EnrichedFileAnalysis:
    """Produit l'analyse enrichie complète à partir d'un CosmicFileReport.

    Une seule passe d'enrichissement : le regroupement par FP se fait sur les
    mouvements bruts, puis chaque mouvement est remplacé UNE fois avec
    OOI + data group + nom du FP (au lieu de deux passes de replace).
    """
    fps = group_by_functional_process(list(file_report.movements))
    for fp in fps:
        # OOI dominant du FP (nom de fichier + signaux des mouvements),
        # utilisé comme fallback pour les mouvements sans signal propre.
        fp_ooi = _infer_fp_object_of_interest(fp.movements, file_report.path)
        new_movements = []
        for m in fp.movements:
            ooi = _infer_object_of_interest(m, fallback=fp_ooi)
            new_movements.append(dataclasses.replace(
                m,
                object_of_interest=ooi,
                data_group=_infer_data_group(m, ooi),
                inferred=True,
                functional_process=fp.name,
            ))
        fp.movements = new_movements
    interval = compute_interval(fps)
    return EnrichedFileAnalysis(
        path=file_report.path,
        language=file_report.language,
        functional_processes=fps,
        interval=interval,
    )


@dataclass
class EnrichedRepoAnalysis:
    """Analyse COSMIC enrichie agrégée sur tout un repo."""
    scope: str
    files: list[EnrichedFileAnalysis] = field(default_factory=list)

    @property
    def interval(self) -> ConfidenceInterval:
        """Intervalle agrégé : somme des bornes de tous les fichiers."""
        low = sum(f.interval.low for f in self.files)
        central = sum(f.interval.central for f in self.files)
        high = sum(f.interval.high for f in self.files)
        hc = sum(f.interval.high_confidence_floor for f in self.files)
        return ConfidenceInterval(
            low=low, central=central, high=high, high_confidence_floor=hc,
        )

    @property
    def uncertain_fps(self) -> list[tuple[str, str]]:
        """Liste (fichier, nom FP) des FP avec incertitude de fusion (L10).

        Permet de pointer exactement où le jugement COSMIC se joue.
        """
        result = []
        for f in self.files:
            for fp in f.functional_processes:
                if fp.has_fusion_uncertainty:
                    result.append((f.path, fp.name))
        return result

    def to_dict(self) -> dict:
        iv = self.interval
        return {
            "scope": self.scope,
            "interval": iv.to_dict(),
            "file_count": len(self.files),
            "uncertain_fp_count": len(self.uncertain_fps),
            "uncertain_fps": [
                {"file": f, "functional_process": n}
                for f, n in self.uncertain_fps
            ],
            "files": [f.to_dict() for f in self.files],
        }


def analyze_repo_enriched(scan_report) -> EnrichedRepoAnalysis:
    """Produit l'analyse enrichie de tout un repo à partir d'un CosmicScanReport.

    Usage :
        from kodoneko_scanner import scan_repo_cosmic
        from kodoneko_metrics.cosmic.analysis_report import analyze_repo_enriched
        r = scan_repo_cosmic('/path/to/repo')
        enriched = analyze_repo_enriched(r)
        print(enriched.interval.label())  # ex: "142 CFP [118–163]"
    """
    files = [analyze_enriched(fr) for fr in scan_report.files]
    return EnrichedRepoAnalysis(scope=scan_report.scope, files=files)
