# Pourquoi l'analyse statique sur-compte les Exits — explication pédagogique

Ce document explique, sur un cas concret, l'écart le plus fréquent entre un
compteur automatique (analyse statique du code) et un comptage COSMIC
rigoureux. C'est la **limite L10** : la non-fusion des messages d'erreur et de
confirmation.

## Le cas concret

Voici un endpoint de création d'Owner typique (Spring MVC, ou son équivalent
FastAPI / Flask) :

```python
@app.post("/owners/new")
def process_creation(owner, result, session=None):
    if result.has_errors:
        return "owners/createForm"      # (1) erreur de validation
    if owner.duplicate:
        return "owners/createForm"      # (2) erreur : doublon
    session.add(owner)                   # écriture en base
    return "redirect:/owners/list"       # (3) succès
```

Il y a **trois `return`** dans ce code. La question est : combien d'Exits
COSMIC cela représente-t-il ?

## Ce que voit l'analyse statique naïve (comptage brut)

Le compteur détecte chaque `return` comme une sortie de données. Il compte
donc **3 Exits** :

| Ligne | Mouvement | Ce que le code montre |
|------:|-----------|------------------------|
| entrée | **Entry** | la requête POST arrive avec les données Owner |
| return (1) | **Exit** | re-render du formulaire (erreur validation) |
| return (2) | **Exit** | re-render du formulaire (doublon) |
| `session.add` | **Write** | persistance de l'Owner |
| return (3) | **Exit** | redirection de confirmation |

**Total brut = 5 CFP** (1 Entry + 1 Write + 3 Exits).

## Ce que compte COSMIC (la règle officielle)

Le manuel COSMIC (Measurement Manual v5.0, Part 2, Guidance Rules 16-19a)
énonce une règle précise :

> **Un seul Exit est identifié pour rendre compte de tous les types de
> messages d'erreur et de confirmation émis par un même functional process,
> quelle qu'en soit la cause.**

Autrement dit, les trois `return` ci-dessus ne sont pas trois sorties de
données distinctes. Ce sont :

- (1) et (2) : deux **messages d'erreur** (le formulaire ré-affiché signale un
  problème) → ils comptent ensemble.
- (3) : un **message de confirmation** (« opération réussie, voici la suite »).

Tous les messages d'erreur ET de confirmation d'un même functional process
**fusionnent en UN SEUL Exit**. Le comptage devient :

| Mouvement | COSMIC |
|-----------|:------:|
| Entry (données Owner entrantes) | 1 |
| Write (persistance) | 1 |
| Exit (messages erreur + confirmation, fusionnés) | 1 |

**Total COSMIC = 3 CFP.**

> Note : ici les trois returns sont tous des messages (erreur ou
> confirmation). Si l'un d'eux renvoyait un **objet d'intérêt différent avec
> ses données** (par exemple la liste paginée des Owners), il compterait comme
> un Exit séparé. La fusion concerne les *messages*, pas les *données métier*.

## La preuve par les exemples officiels

Cette règle n'est pas une interprétation : elle est appliquée telle quelle
dans les case studies COSMIC de référence.

- **C-REG v2.0.1, « Add a Professor »** : la spécification liste trois messages
  d'erreur distincts (« ID inconnu », « nom déjà existant », « données
  invalides »). Le comptage officiel les fusionne en **un seul Exit
  erreur/confirmation**. Total : 4 CFP (Entry + Read + Write + 1 Exit).

- **Web Advice Module v1.1.1** : chaque tableau de functional process montre
  une unique ligne « Error/Confirmation messages × 1 », quel que soit le
  nombre de causes d'erreur possibles.

## Comment kodoneko gère cet écart : l'intervalle de confiance

L'analyse statique ne peut pas toujours savoir si un `return` est un message
ou une donnée métier — cela dépend des Functional User Requirements, qui ne
sont pas dans le code. Plutôt que de trancher arbitrairement, kodoneko produit
un **intervalle** :

```
TOTAL : 4 CFP [4–5]
  borne haute  : 5 CFP   <- comptage brut (chaque return = 1 Exit)
  central      : 4 CFP   <- frequency rule appliquee (fusion des messages)
  borne basse  : 4 CFP   <- hypothese de fusion maximale
```

La **vérité COSMIC (3-4 CFP selon l'interprétation)** est encadrée par
l'intervalle. La valeur centrale (4) applique la fusion et constitue la
meilleure estimation automatique. La borne haute (5) correspond à ce que
verrait un compteur naïf sans connaissance de la règle.

## En résumé

| | Exits comptés | Total | Pourquoi |
|---|:---:|:---:|---|
| Analyse statique naïve | 3 | 5 | chaque `return` = 1 Exit |
| **COSMIC (règle 16-19a)** | **1** | **3-4** | tous les messages erreur/confirmation = 1 Exit |
| kodoneko central | 1 (fusionné) | 4 | applique la frequency rule |

L'écart vient entièrement de la façon de compter les sorties : le code montre
des `return` (artefacts d'implémentation), COSMIC compte des *mouvements de
données fonctionnels*. Un même functional process ne « sort » qu'un seul type
de message vers l'utilisateur, même s'il y a dix `return` dans le code.
