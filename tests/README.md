# tests/ — suite de non-régression de repo-map

But : **arrêter de recréer les fixtures en scratchpad à chaque session.** Chaque brique
de résolution de scope (piste #3) est figée ici comme un cas reproductible. Le mantra du
projet — *seul le test réel révèle les trous* — devient une commande.

## Lancer

```sh
# depuis la racine du repo (repo-map/), avec le python du venv (tree-sitter)
./.venv/Scripts/python.exe tests/run_tests.py
```

Sortie attendue : `== TOUT PASSE ==`. En cas d'échec, chaque écart est listé
(`manquante` = arête attendue absente, `en trop` = arête produite mais non attendue).

Options :
- `--only py_self_cls` : ne lancer qu'une fixture.
- `--record` : refiger tous les `expected.json` depuis la sortie courante.
  **À n'utiliser qu'après avoir VÉRIFIÉ à la main que les arêtes produites sont
  correctes** — sinon on fige un bug en « comportement attendu ».

## Comment ça marche

`run_tests.py` importe `build_graph.build()` et, pour chaque sous-dossier de
`fixtures/`, compare **l'ensemble EXACT** des arêtes du graphe (`graph["edges"]`,
nœuds `"relpath::symbole"`) à celui déclaré dans le `expected.json` de la fixture.

Pourquoi l'égalité d'ensemble et pas un simple « contient l'arête X » : un bug de
résolution se manifeste autant par une arête **en trop** (fan-out vers un homonyme, faux
builtin résolu) que par une arête **manquante**. L'égalité attrape les deux.

Trois **smoke / régressions** finaux (hors `--only`) complètent les fixtures d'arêtes :
- **smoke** : indexer repo-map lui-même ne doit ni crasher ni rendre 0 arête (pas de
  compte exact — trop fragile, le chiffre bouge à chaque évolution du code).
- **régression `where_is`** (bug du 06/07, denta-scribe) : le tri de `where_is` retombait
  sur la comparaison de deux `dict` à rang+nom égaux → `'<' not supported between instances
  of 'dict' and 'dict'`. La query vide (`where_is("")`) matche tous les symboles = collisions
  massives = déclencheur garanti ; le test vérifie qu'aucun crash ne survient.
- **`.repomapignore`** : fige la sémantique de `_ignored` (nom nu / préfixe de dossier /
  glob) et vérifie bout-en-bout que le `.repomapignore` du repo exclut bien `tests/fixtures`
  du build.

## Les fixtures (une par mécanisme de la piste #3)

| Dossier             | Mécanisme testé (session du journal)                          |
|---------------------|---------------------------------------------------------------|
| `py_self_cls`       | `self.`/`cls.` résolus par scope, filtre builtin sauté, pas de fan-out (s.1) |
| `js_this`           | `this.foo()` résolu par scope en TS (s.2)                     |
| `py_inheritance`    | méthode héritée `self.shared()` remontée jusqu'à la classe mère (s.3) |
| `ts_extends`        | idem via la clause `extends` en TS (s.4)                      |
| `py_named_imports`  | `from mod import a, b as c` : nom importé résolu vers le bon fichier, alias, contourne builtin (s.5) |
| `js_named_imports`  | `import { a, b as c } from './mod'` : idem JS/TS (s.6)        |
| `py_portee_locale`  | **portée lexicale** : `main()` local ≠ `main()` du voisin ; closure ; une méthode homonyme ne capte PAS un appel direct (03/08) |
| `ts_portee_locale`  | idem, décalqué du cas réel denta-scribe (deux écrans, un `loadPatients` chacun) (03/08) |

⚠️ `*_portee_locale` sont les seules fixtures qui figent une **suppression** d'arêtes.
Toutes les autres figent l'invariant « au pire on ajoute une arête, jamais on n'en perd » ;
la portée locale l'assume à un seul endroit, parce qu'un faux lien entre deux fichiers coûte
plus cher qu'une arête manquante (il fait mentir `who_references` / `what_it_uses`). Le
garde-fou est dans `gamma.py` : dès qu'une définition locale n'est PAS réellement
atteignable (méthode de classe, closure hors portée), le fan-out d'avant doit revenir.

Chaque fixture met les **homonymes dans des fichiers différents** : le nœud d'arête est
`fichier::nom` (sans la classe), donc c'est le seul moyen de distinguer une résolution
propre d'un fan-out dans l'assertion.

## Ajouter un cas

1. Créer `fixtures/<nom>/` avec le(s) fichier(s) de code minimal exerçant le mécanisme.
   Mettre en tête un commentaire décrivant l'**intention** (quelle arête doit / ne doit
   pas apparaître).
2. Écrire `fixtures/<nom>/expected.json` : `{ "description": "...", "edges": [["a::x","b::y"], ...] }`.
   Calculer les arêtes à la main d'abord ; lancer ; ajuster la fixture (pas l'attente)
   si le moteur ne produit pas ce qu'on visait.
3. Quand l'inférence de type (`obj.foo()`) sera codée : ajouter `py_type_infer` /
   `js_type_infer` sur le même modèle.

## Pollution du dogfooding — RÉSOLU (08/07) via `.repomapignore`

Historiquement, `build(repo-map)` (repo-map indexé sur lui-même) incluait `tests/fixtures/`
(~31 arêtes parasites, symboles bidon `parse`/`helper`/`foo`… collisionnant avec le vrai
code). `EXCLUDE_DIRS` n'exclut **pas** `tests` à dessein — les tests d'un repo *utilisateur*
méritent d'être cartographiés.

La réponse est un ignore **par-repo**, pas un défaut global : un fichier **`.repomapignore`**
à la racine du repo ciblé (style `.gitignore` : un motif par ligne, `#` = commentaire),
**fusionné** avec `EXCLUDE_DIRS`. Sémantique (cf. `build_graph._ignored`) :
- **nom nu** sans glob (`fixtures`, `node_modules`) → match n'importe quel segment de chemin ;
- **motif avec `/` ou glob** (`tests/fixtures`, `scripts/*`, `*.gen.ts`) → match le chemin
  lui-même **ou tout ce qui est sous lui** (préfixe de dossier).

Le repo-map en fournit un (`repo-map/.repomapignore`) qui exclut `tests/fixtures`. Même
usage sur un repo utilisateur : `design_handoff/`, scripts jetables, dossiers générés, etc.
