; tags.scm — JavaScript (et JSX)
; Captures au format attendu par build_graph.py : definition.* / reference.*
; IMPORTANT : chaque @definition.* porte sur l'IDENTIFIANT du nom ; son nœud PARENT
; est l'englobant porteur des bornes (line/end_line). Cohérent avec le tags.scm Python.

; --- définitions : fonctions ---
(function_declaration
  name: (identifier) @definition.function)

(generator_function_declaration
  name: (identifier) @definition.function)

; const f = (...) => {...}  /  const f = function(){...}
; (le parent = variable_declarator, qui englobe « f = … » corps compris)
(variable_declarator
  name: (identifier) @definition.function
  value: [(arrow_function) (function_expression)])

; méthodes de classe / d'objet
(method_definition
  name: (property_identifier) @definition.function)

; --- définitions : classes ---
(class_declaration
  name: (identifier) @definition.class)

; --- définitions : variables/constantes (filtrées AU NIVEAU MODULE côté build_graph) ---
; NB : capture large ; les arrow/function-expr ci-dessus sont dédupliquées (priorité fonction).
(variable_declarator
  name: (identifier) @definition.variable)

; --- références (appels) ---
; appel direct :  search(...)
(call_expression
  function: (identifier) @reference.call)

; appel de méthode/attribut :  obj.method(...)
(call_expression
  function: (member_expression
    property: (property_identifier) @reference.call))

; récepteur `this` d'un appel de méthode :  this.method(...) — analogue à self./cls. en
; Python. Permet à build_graph.py de résoudre vers la méthode de la classe englobante au
; lieu d'un appariement par nom (et de contourner le filtre builtin homonyme). Corrélé à
; @reference.call ci-dessus via leur member_expression parent commun (.parent.id).
(call_expression
  function: (member_expression
    object: (this) @reference.receiver
    property: (property_identifier) @reference.call))

; récepteur IDENTIFIANT d'un appel de méthode :  obj.method(...) — `obj` capturé comme
; receiver pour l'INFÉRENCE DE TYPE (si `const obj = new Ctor()`, résoudre vers Ctor.method
; au lieu d'un fan-out par nom). Disjoint du cas `this` ci-dessus (nœud `this` != identifier).
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

; import_statement ENTIER : build_graph.py le parcourt pour lier chaque NOM importé nommé
; (`import { a, b as c } from './mod'`) à son module source, et résoudre un appel direct
; `a()` vers le bon fichier au lieu d'un fan-out. (default `import x` et `* as ns` = nom de
; module, hors scope ici -> relèvent de l'inférence de type.)
(import_statement) @reference.import.stmt

; export default d'une classe/fonction : nom du symbole exporté par défaut de CE fichier,
; pour qu'un `import Foo from './ce-fichier'` (nom local quelconque) résolve vers lui. Le
; `default` discrimine l'export par défaut des exports nommés (`export class`/`function`).
(export_statement
  "default"
  declaration: (class_declaration name: (identifier) @reference.export.default))
(export_statement
  "default"
  declaration: (function_declaration name: (identifier) @reference.export.default))
