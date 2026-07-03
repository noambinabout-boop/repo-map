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

Un **smoke test** final indexe repo-map lui-même : il doit ne pas crasher et produire
> 0 arête (pas d'assertion de compte exact — trop fragile, le chiffre bouge à chaque
évolution du code).

## Les fixtures (une par mécanisme de la piste #3)

| Dossier             | Mécanisme testé (session du journal)                          |
|---------------------|---------------------------------------------------------------|
| `py_self_cls`       | `self.`/`cls.` résolus par scope, filtre builtin sauté, pas de fan-out (s.1) |
| `js_this`           | `this.foo()` résolu par scope en TS (s.2)                     |
| `py_inheritance`    | méthode héritée `self.shared()` remontée jusqu'à la classe mère (s.3) |
| `ts_extends`        | idem via la clause `extends` en TS (s.4)                      |
| `py_named_imports`  | `from mod import a, b as c` : nom importé résolu vers le bon fichier, alias, contourne builtin (s.5) |
| `js_named_imports`  | `import { a, b as c } from './mod'` : idem JS/TS (s.6)        |

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

## Limite connue — pollution du dogfooding

`build(repo-map)` (repo-map indexé sur lui-même) inclut désormais `tests/fixtures/` :
~31 arêtes parasites sur ~81, avec des symboles bidon (`parse`, `helper`, `foo`…) qui
collisionnent avec le vrai code. `EXCLUDE_DIRS` n'exclut pas `tests` (à dessein : les
tests d'un repo *utilisateur* méritent d'être cartographiés). Si le dogfooding de
repo-map sur lui-même devient gênant, la vraie réponse est un mécanisme d'ignore
par-repo (ex. `.repomapignore`), pas un défaut global — chantier séparé.
