; tags.scm — TypeScript (et TSX, même grammaire)
; Captures au format attendu par build_graph.py : definition.* / reference.*
; Comme en JS, chaque @definition.* porte sur l'identifiant du nom (parent = bornes).
; ⚠ En TS le nom des classes/interfaces/types est un (type_identifier), pas (identifier).

; --- définitions : fonctions ---
(function_declaration
  name: (identifier) @definition.function)

(variable_declarator
  name: (identifier) @definition.function
  value: [(arrow_function) (function_expression)])

(method_definition
  name: (property_identifier) @definition.function)

; signatures de méthode (interface / classe abstraite) = surface d'API utile
(method_signature
  name: (property_identifier) @definition.function)

(abstract_method_signature
  name: (property_identifier) @definition.function)

; --- définitions : classes / interfaces / enums (= types porteurs de structure) ---
(class_declaration
  name: (type_identifier) @definition.class)

(abstract_class_declaration
  name: (type_identifier) @definition.class)

(interface_declaration
  name: (type_identifier) @definition.class)

(enum_declaration
  name: (identifier) @definition.class)

; --- définitions : variables / alias de type (filtrés AU NIVEAU MODULE) ---
(type_alias_declaration
  name: (type_identifier) @definition.variable)

(variable_declarator
  name: (identifier) @definition.variable)

; --- références (appels) ---
(call_expression
  function: (identifier) @reference.call)

(call_expression
  function: (member_expression
    property: (property_identifier) @reference.call))

; récepteur `this` d'un appel de méthode :  this.method(...) — analogue à self./cls. en
; Python (mécanisme identique à la version JS). Résout vers la méthode de la classe
; englobante ; corrélé à @reference.call via leur member_expression parent commun.
(call_expression
  function: (member_expression
    object: (this) @reference.receiver
    property: (property_identifier) @reference.call))

; récepteur IDENTIFIANT d'un appel de méthode :  obj.method(...) — `obj` capturé pour
; l'INFÉRENCE DE TYPE (si `const obj = new Ctor()`, résoudre vers Ctor.method au lieu d'un
; fan-out par nom). Disjoint du cas `this` ci-dessus (nœud `this` != identifier).
(call_expression
  function: (member_expression
    object: (identifier) @reference.receiver
    property: (property_identifier) @reference.call))

; affectation `const x = new Ctor(...)` : inférence de type (résoudre x.foo() vers Ctor).
; Capturée entière puis parcourue dans build_graph (name = variable, value.constructor = type).
(variable_declarator
  value: (new_expression)) @typeinfer.assign

; --- références (imports) : construit le graphe FICHIER -> FICHIER (en plus des appels) ---
; import x from './foo' / import { a } from '../bar'  (source = la string littérale, guillemets inclus)
(import_statement
  source: (string) @reference.import)
; export { c } from './baz'  /  export * from './qux'  (ré-exports = dépendance aussi)
(export_statement
  source: (string) @reference.import)

; import_statement ENTIER : parcouru par build_graph.py pour lier chaque nom importé nommé
; (`import { a, b as c } from './mod'`) à son module source (même méca que la version JS).
; default `import x` et `import * as ns` = nom de module -> hors scope (inférence de type).
(import_statement) @reference.import.stmt

; export default d'une classe/fonction : nom du symbole exporté par défaut de CE fichier,
; pour qu'un `import Foo from './ce-fichier'` (nom local quelconque) résolve vers lui. Le
; `default` discrimine l'export par défaut. ⚠ En TS le nom de classe est un type_identifier.
(export_statement
  "default"
  declaration: (class_declaration name: (type_identifier) @reference.export.default))
(export_statement
  "default"
  declaration: (function_declaration name: (identifier) @reference.export.default))
