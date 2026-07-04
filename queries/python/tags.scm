; tags.scm — Python
; Motifs tree-sitter pour repérer DÉFINITIONS et RÉFÉRENCES de symboles.
; Le nom de capture encode le rôle : definition.* / reference.*

; --- définitions ---
(function_definition
  name: (identifier) @definition.function)

(class_definition
  name: (identifier) @definition.class)

; assignations (constantes/flags : ENABLE_X = ...). Capturées largement ici ;
; build_graph.py ne GARDE que celles de NIVEAU MODULE (les vraies constantes du
; fichier), pas les variables locales aux fonctions.
(assignment
  left: (identifier) @definition.variable)

; affectation ENTIÈRE `x = Ctor(...)` : parse_file en extrait (variable -> type de l'objet
; construit) pour l'INFÉRENCE DE TYPE — résoudre plus tard `x.foo()` vers la classe Ctor au
; lieu d'un fan-out par nom (cf. build_graph.assemble). Capturée entière puis parcourue (left
; = variable, right = call dont la fonction donne le nom de type) ; même méca que reference.import.from.
(assignment) @typeinfer.assign

; --- références (appels) ---
; appel direct :  search(...)
(call
  function: (identifier) @reference.call)

; appel de méthode/attribut :  self._rank(...) / obj.method(...)
(call
  function: (attribute
    attribute: (identifier) @reference.call))

; récepteur d'un appel d'attribut SIMPLE (identifiant seul, pas une chaîne self.x.y()) —
; permet à build_graph.py de distinguer self./cls. et de résoudre vers la classe englobante
; au lieu d'un simple appariement par nom. Corrélé à la capture reference.call ci-dessus via
; leur noeud `attribute` parent commun (cf. parse_file : corrélation par .parent.id).
(call
  function: (attribute
    object: (identifier) @reference.receiver
    attribute: (identifier) @reference.call))

; --- références (imports) : construit le graphe FICHIER -> FICHIER (en plus des appels) ---
; import x / import x.y  (le texte du nœud = le chemin pointé, ex "os.path")
(import_statement
  name: (dotted_name) @reference.import)
; import x as y  (le nom réel est dans aliased_import.name)
(import_statement
  name: (aliased_import
    name: (dotted_name) @reference.import))
; from x.y import z  (absolu)
(import_from_statement
  module_name: (dotted_name) @reference.import)
; from . import z / from .x import z / from ..x import z  (relatif, dots inclus)
(import_from_statement
  module_name: (relative_import) @reference.import)

; import_from_statement ENTIER : build_graph.py le parcourt pour lier chaque NOM importé
; (`from mod import a, b as c`) à son module source, et résoudre un appel direct `a()` vers
; le bon fichier au lieu d'un fan-out par nom. (Le module lui-même reste capturé ci-dessus
; comme @reference.import pour le graphe fichier->fichier ; ici on veut les noms importés.)
(import_from_statement) @reference.import.from
