# Analyse COSMIC enrichie : intervalle de confiance + tableau façon manuel

**Version** : kodoneko_metrics 2.10.0
**Auteur** : Benoît Moraillon

## Motivation

Le comptage COSMIC rigoureux exige l'identification des Functional User
Requirements, des objets d'intérêt et des fréquences d'occurrence — des
jugements sémantiques que l'analyse statique ne peut pas toujours trancher.
Plutôt que de prétendre à un chiffre exact, kodoneko produit désormais un
**estimateur avec intervalle de confiance** et un **détail tabulaire** façon
case study COSMIC (C-REG, Web Advice Module).

Distinction de responsabilité : **kodoneko** est le compteur (moteur de mesure
avec sa rigueur méthodologique propre). **Calibrix** est le produit qui
l'exploite. Cette fonctionnalité vit dans kodoneko.

## Ce que ça produit

Pour un fichier ou un repo :

1. **Regroupement par functional process** (heuristique : un Entry ouvre un FP).
2. **Inférence des objets d'intérêt et data groups** — estimés par analyse de
   l'extrait de code, filtrant les noms techniques (exceptions, types,
   primitives). Marqués `inferred=True` : ce sont des estimations, pas des
   certitudes.
3. **Intervalle de confiance A+B** :
   - **A (bornes de jugement)** : la frequency rule COSMIC (Guidance Rules
     16-19a) fusionne les Exits erreur/confirmation en 1 par FP. Le cas L10
     (Spring MVC à returns multiples) est traité : si un FP a une action
     (Write) et plusieurs returns, l'hypothèse basse fusionne les returns
     surnuméraires en 1 message.
   - **B (confiance détecteurs)** : plancher = mouvements 'high' seuls.
   - Borne basse = min(strict, plancher_HC) ; centrale = strict ;
     haute = brut.
4. **Tableau détaillé** façon manuel : par FP, chaque data movement avec type
   (E/R/W/X), OOI estimé, data group estimé, détecteur, confiance, CFP.
5. **Localisation des FP incertains** : les FP avec écart borne basse/haute
   (incertitude de fusion L10) sont listés explicitement.

## API

```python
from kodoneko_scanner import scan_repo_cosmic
from kodoneko_metrics.cosmic import (
    analyze_repo_enriched, render_repo_markdown,
    analyze_enriched, render_markdown, render_text,
)

# Repo entier
r = scan_repo_cosmic('/path/to/repo')
enriched = analyze_repo_enriched(r)
print(enriched.interval.label())        # ex: "142 CFP [118–163]"
print(render_repo_markdown(enriched))   # rapport complet façon manuel

# Fichier unique
fr = CosmicAnalyzer().analyze_file('OwnerController.java')
fa = analyze_enriched(fr)
print(render_text(fa))                  # détail console
```

## Honnêteté méthodologique

- L'intervalle **encadre** la vérité COSMIC ; il ne la devine pas. La valeur
  réelle est dans [low, high], avec central comme meilleure estimation.
- Les OOI et data groups sont **estimés** et marqués comme tels.
- Un comptage COSMIC certifié requiert toujours un mesureur humain analysant
  les FUR. kodoneko fournit un estimateur reproductible et auditable, idéal
  pour une mesure continue et reproductible, pas un certificat ISO 19761.

## Validation

Logique calée sur les exemples officiels :
- C-REG v2.0.1 : "Add a Professor" (3 messages erreur → 1 Exit), enquire-
  before-update = 2 FP.
- Web Advice Module v1.1.1 : "Error/Confirmation messages X 1", 4 objets
  d'intérêt = 4 Exits.
- COSMIC MM v5.0 Part 2, Guidance Rules 16-19.

10 tests de régression dans test_analysis_report.py.

---

## v2.10.2 : corrections suite à la validation OwnerController (main)

Le scan réel d'OwnerController (version main, 8 endpoints) a révélé trois
défauts, tous corrigés :

### 1. Fusion L10 élargie (ne nécessite plus de Write)

Avant : la fusion des returns multiples ne s'appliquait que si le FP avait une
écriture (`if writes and len(generic_exits) > 1`). Conséquence : un GET de
recherche avec 3 returns alternatifs (re-render form, redirect, liste) n'était
pas fusionné. Or COSMIC fusionne les messages erreur/confirmation quel que soit
le type de requête.

Après : la fusion s'applique dès qu'il y a plusieurs Exits génériques
(1 Exit données + 1 message fusionné), GET comme POST. FP4 (processFindForm)
passe ainsi de strict=5 à strict=4.

### 2. Borne basse réaliste

Avant : `low = min(strict, plancher_HC)`. Comme tous les Exits Spring sont en
confiance 'medium', le plancher HC les excluait tous → borne basse à 12 sur
OwnerController (irréaliste : supposait que tous les Exits sont faux).

Après : `low = strict` (hypothèse de fusion maximale plausible). Le plancher HC
reste exposé séparément comme garde-fou détection. L'intervalle OwnerController
passe de [12–24] à [22–24] — resserré autour de la réalité COSMIC (20-21).

### 3. FP préambule éliminé

Avant : un Read de méthode partagée (@ModelAttribute findOwner) apparaissant
avant le 1er endpoint formait un "FP préambule" fantôme.

Après : les mouvements orphelins (avant le 1er Entry) sont rattachés au premier
FP réel. Si aucun endpoint n'existe, ils forment un FP "hors endpoint".
OwnerController passe de 8 à 7 FP, le findById L67 rejoint FP1.

### Résultat sur OwnerController

| | Avant | Après | Manuel COSMIC |
|---|---|---|---|
| Intervalle | 23 [12–24] | **22 [22–24]** | 20-21 |
| Nombre de FP | 8 | 7 | 7 |

Le central (22) est à +1/+2 du comptage manuel validé contre C-REG, et
l'intervalle est désormais exploitable.

### Document pédagogique

Ajout de PEDAGOGIE_FUSION_EXITS.md : explication pas à pas, sur un cas concret
(POST création à 3 returns), de pourquoi l'analyse statique compte 5 CFP et
COSMIC 3-4. Avec preuve par C-REG et Web Advice Module.

---

## v2.10.3 → v2.11.0 : rendu HTML pédagogique + notebook produit fini

### Borne basse = fusion maximale (v2.10.3)

`compute_interval` : la borne basse est désormais `min_cfp` (tous les Exits d'un
FP fusionnés en 1), au lieu de `min(strict, plancher_HC)`. Garantit que
l'intervalle encadre la vérité COSMIC par le bas. OwnerController : [12–24] →
[19–24], qui contient le comptage manuel validé (20-21).

Nouvelle propriété `FunctionalProcessView.min_cfp` : hypothèse de fusion
maximale. `has_fusion_uncertainty` compare désormais min_cfp et raw_cfp.

### Module html_formatter (v2.11.0)

Nouveau rendu HTML pédagogique, pensé pour un lecteur humain non-spécialiste :
- `render_html(analysis, standalone=False)` : rapport d'un fichier
- `render_repo_html(repo_analysis, standalone=False)` : synthèse d'un dépôt
- `standalone=True` : document HTML autonome (export fichier partageable)

Composants pédagogiques : badges colorés par type de mouvement (E/X/R/W),
légende, encadré « Comment lire cette estimation » détaillant les trois bornes,
avertissement explicite sur le statut d'estimation (vs certification), et
bandeau signalant les processus à comptage ambigu avec explication de la règle
de fusion 16-19a.

CSS inline, aucune dépendance externe. Compatible IPython.display.HTML
(notebook) et export navigateur.

### Notebook 07 — finition produit

- En-tête entièrement réécrit : 6 sections pédagogiques (qu'est-ce que COSMIC,
  comment kodoneko estime et pourquoi c'est une estimation, choix
  d'implémentation, références officielles, portée/limites, prérequis).
- Section 8 élargie à 3 dépôts publics (spring-petclinic, fastapi-template,
  realworld-django) avec liste configurable.
- Cellules de rendu HTML : rapport fichier, synthèse dépôt, export autonome.

Tests : 138 (ajout de 4 tests HTML). Total projet : 350.

---

## v2.11.0 → v2.12.0 : lisibilité des rendus

Trois améliorations de présentation, suite aux retours d'usage :

### 1. Suppression du jargon de conception dans les rendus utilisateur

Les rendus HTML, Markdown et texte ne mentionnent plus les noms internes de
règles ou de limites (« Rule 16-19a », « L10 », « frequency rule »). Le bandeau
de sorties multiples explique désormais en langage clair : « les messages
d'erreur et de confirmation d'un même processus comptent ensemble pour une seule
sortie de données ». Les noms internes restent dans les commentaires de code et
la documentation technique, pas dans ce que voit l'utilisateur final.

### 2. Nom de la fonction dans les processus fonctionnels

Les FP affichent désormais le nom de la fonction/méthode déclencheuse :
« FP1 : processCreationForm() — début ligne 72, détecté par le pattern
spring_post_mapping » au lieu de « FP1 (L72, spring_get_mapping) ».

Nouveaux champs sur FunctionalProcessView : function_name, start_line, detector.
Helper _function_name_from_movement (regex multi-langage : def Python,
function/method JS, signature Java).

### 3. Inférence d'objet d'intérêt à deux niveaux

Les colonnes « objet d'intérêt » et « data group » étaient quasi toujours vides
car l'ancienne heuristique cherchait un PascalCase dans chaque extrait isolé —
or les instances sont en minuscule (`session.add(owner)`).

Nouvelle approche à deux niveaux :
- niveau mouvement : PascalCase dans l'extrait (`session.get(Owner, ...)`) ;
- niveau processus : OOI dominant du FP (signal le plus fréquent) ou déduit du
  nom de fichier (`OwnerController.java` → Owner, `pet_service.py` → Pet) ;
- les mouvements sans signal propre héritent de l'OOI du FP.

Helpers : _ooi_from_filename, _ooi_from_excerpt, _infer_fp_object_of_interest.
Résultat : les colonnes sont désormais renseignées sur du code réel.

Tests : 142 (ajout de 4). Total projet : 354.

---

## v2.12.0 → v2.12.1 : fusion des colonnes de présentation

Dans le rendu HTML, les colonnes « Objet d'intérêt » et « Data group » sont
fusionnées en une seule colonne **« Données manipulées »** affichant l'objet
métier (ex: Owner). La distinction entrée/sortie vs persistance que portait le
data group est déjà donnée par la colonne Type (E/X vs R/W), donc l'affichage
séparé était redondant.

Le champ `data_group` reste calculé et présent dans `to_dict()` (export JSON) —
seul l'affichage HTML est simplifié. Aucune perte d'information.
