"""build_graph.py — construit code_graph.json à partir d'un dossier de code.

Principe :
1. tree-sitter parse chaque fichier (texte -> arbre), selon son LANGAGE (déduit de
   l'extension : Python, JavaScript/JSX, TypeScript/TSX).
2. La requête tags.scm du langage étiquette les noeuds : definition.* / reference.*
3. Pour chaque référence (appel), on trouve le symbole ENGLOBANT par PLAGE DE LIGNES
   (le def/class dont l'intervalle contient l'appel, le plus imbriqué). D'où le
   graphe "qui appelle qui". Méthode indépendante du langage (vs une remontée d'AST
   avec des types de noeuds propres à chaque grammaire).
4. On résout chaque appel par NOM vers les définitions de ce nom (approximatif mais
   utile — pas de résolution de SCOPE/type, choix assumé, valable cross-langage).
   EXCEPTION (piste #3, Python) : self.foo()/cls.foo() sont résolus par SCOPE vers la
   méthode de la classe qui entoure lexicalement l'appel, quand elle existe dans ce
   fichier — évite qu'un builtin homonyme (list/parse/format...) fasse disparaître la
   méthode du graphe, et qu'un homonyme d'une classe SANS RAPPORT pollue les arêtes.
5. En PLUS des appels : un graphe d'imports FICHIER -> FICHIER (résolu par chemin, avec
   repli par suffixe en Python) muscle le PageRank — capture la structure JSX/composants
   qui échappe au graphe d'appels pur (cf. limite mesurée le 29/06 sur du React/Expo).
   Ce graphe reste interne au ranking : il n'apparaît jamais dans `edges` (who_references).

Sortie = code_graph.json : artefact unique servant l'outil MCP ET la viz.

Multi-langage : générique par DESIGN (un tags.scm par langage). Ajouter un langage =
ajouter une grammaire + un tags.scm + une ligne dans LANGS, sans toucher le moteur.

Usage : python build_graph.py <dossier> [-o code_graph.json]
"""
import sys
import os
import json
import argparse
from collections import defaultdict

import builtins as _builtins

import tree_sitter_python as tsp
import tree_sitter_javascript as tsjs
import tree_sitter_typescript as tsts
from tree_sitter import Language, Parser, Query, QueryCursor

from pagerank import pagerank

QUERIES_ROOT = os.path.join(os.path.dirname(__file__), "queries")

# Bumpée à chaque changement de schéma des fichiers cachés (ex : ajout du champ
# "imports", ou déplacement du rank hors du cache disque vers un calcul à la demande).
# server.py compare ce numéro à celui du cache disque pour forcer un rebuild complet
# plutôt que de mélanger silencieusement ancien/nouveau schéma.
SCHEMA_VERSION = 11

# noms à NE PAS résoudre comme symboles internes (sinon les appels aux builtins/
# méthodes ubiquitaires polluent le PageRank en pointant un symbole homonyme).
PY_BUILTINS = set(dir(_builtins))
# JS/TS : globals + méthodes de prototype ultra-communes (capturées comme appels
# `obj.map(...)` -> "map"). On les neutralise pour éviter qu'un symbole interne
# homonyme n'absorbe tous ces appels. La sous-pondération 1/fan-in est un 2e filet.
JS_BUILTINS = {
    "log", "error", "warn", "info", "debug", "assert", "trace",
    "map", "filter", "forEach", "reduce", "reduceRight", "find", "findIndex",
    "some", "every", "includes", "indexOf", "lastIndexOf", "slice", "splice",
    "push", "pop", "shift", "unshift", "concat", "join", "flat", "flatMap",
    "keys", "values", "entries", "fill", "copyWithin", "reverse", "sort", "at",
    "then", "catch", "finally", "resolve", "reject", "all", "allSettled", "race",
    "parse", "stringify", "assign", "freeze", "create", "from", "of", "isArray",
    "toString", "valueOf", "hasOwnProperty", "isInteger", "isNaN", "now",
    "require", "setTimeout", "setInterval", "clearTimeout", "clearInterval",
    "test", "exec", "match", "matchAll", "replace", "replaceAll", "search",
    "trim", "trimStart", "trimEnd", "toLowerCase", "toUpperCase", "normalize",
    "charAt", "charCodeAt", "codePointAt", "startsWith", "endsWith",
    "padStart", "padEnd", "repeat", "split", "substring", "substr",
    "bind", "call", "apply", "addEventListener", "removeEventListener",
    "useState", "useEffect", "useRef", "useMemo", "useCallback", "useContext",
    "useReducer", "useLayoutEffect", "round", "floor", "ceil", "abs", "min",
    "max", "random", "pow", "sqrt", "json", "text", "fetch",
}


def _make_spec(lang_obj, tags_subdir, builtins):
    """Compile la grammaire + sa requête une fois (coûteux), rend une spec réutilisable."""
    language = Language(lang_obj)
    with open(os.path.join(QUERIES_ROOT, tags_subdir, "tags.scm"), encoding="utf8") as f:
        query = Query(language, f.read())
    return {"parser": Parser(language), "query": query, "builtins": builtins}


# registry des langages — chargée à l'import (compile les requêtes une fois)
_PY = _make_spec(tsp.language(), "python", PY_BUILTINS)
_JS = _make_spec(tsjs.language(), "javascript", JS_BUILTINS)
_TS = _make_spec(tsts.language_typescript(), "typescript", JS_BUILTINS)
_TSX = _make_spec(tsts.language_tsx(), "typescript", JS_BUILTINS)

# extension (minuscule) -> spec de langage
LANGS = {
    ".py": _PY,
    ".js": _JS, ".jsx": _JS, ".mjs": _JS, ".cjs": _JS,
    ".ts": _TS, ".mts": _TS, ".cts": _TS,
    ".tsx": _TSX,
}

# union de tous les builtins (l'index `symbols` est inter-langages ; on exclut large
# pour ne pas créer de fausses arêtes vers un homonyme builtin d'un autre langage).
ALL_BUILTINS = PY_BUILTINS | JS_BUILTINS

# récepteurs qui désignent À COUP SÛR l'instance de la classe englobante lexicalement :
# self/cls (Python), this (JS/TS). Un appel `<recepteur>.foo()` est alors résolu vers la
# méthode de cette classe (par scope) plutôt que par appariement de nom global, et échappe
# au filtre ALL_BUILTINS (une méthode homonyme d'un builtin ne doit pas disparaître).
# Assumé pour `this` : imprécis si l'appel est dans une fonction classique imbriquée où
# `this` est rebindé dynamiquement — mais le repli par nom ne perd jamais d'arête (cf.
# assemble()), donc le pire cas est identique au comportement d'avant.
SELF_RECEIVERS = {"self", "cls", "this"}

# dossiers jamais indexés (deps, build, vcs…)
EXCLUDE_DIRS = {
    ".venv", "venv", "node_modules", "__pycache__", ".git", ".hg", ".svn",
    "dist", "build", ".next", ".nuxt", "out", "coverage", ".turbo",
    ".expo", ".cache", "vendor",
}


def _enclosing_name(scopes, line):
    """Nom du def/class dont la PLAGE [line, end_line] contient `line`, le plus imbriqué
    (intervalle le plus petit). '<module>' si la ligne n'est dans aucun scope."""
    best = None
    for d in scopes:
        if d["line"] <= line <= d["end_line"]:
            if best is None or (d["end_line"] - d["line"]) < (best["end_line"] - best["line"]):
                best = d
    return best["name"] if best else "<module>"


def _enclosing_class(scopes, line):
    """Comme _enclosing_name, mais restreint aux scopes kind == 'class' — pour résoudre
    self.foo()/cls.foo() vers la classe qui entoure LEXICALEMENT l'appel. Rend le dict
    complet (pas juste le nom) pour que l'appelant teste l'inclusion d'une méthode
    candidate dans ses bornes [line, end_line]. None si aucune classe n'entoure `line`."""
    best = None
    for d in scopes:
        if d["kind"] != "class":
            continue
        if d["line"] <= line <= d["end_line"]:
            if best is None or (d["end_line"] - d["line"]) < (best["end_line"] - best["line"]):
                best = d
    return best


def _base_name(node):
    """Nom simple d'un noeud désignant une classe de base, résolu ensuite PAR NOM comme le
    reste. `A` -> 'A' ; `pkg.Base`/`ns.Base` (attribute Python ou member_expression JS/TS) ->
    'Base' (dernier segment). Tout le reste (mixin `f()`, générique complexe, kwarg) -> None,
    ignoré."""
    if node.type in ("identifier", "type_identifier"):
        return node.text.decode("utf8")
    if node.type == "attribute":          # Python : pkg.Base
        attr = node.child_by_field_name("attribute")
        return attr.text.decode("utf8") if attr is not None else None
    if node.type == "member_expression":  # JS/TS : ns.Base
        prop = node.child_by_field_name("property")
        return prop.text.decode("utf8") if prop is not None else None
    return None


def _class_bases(class_node):
    """Noms des classes de base (héritage) d'une définition de classe, multi-langage :
      - Python : champ `superclasses` (argument_list) — `class B(A, pkg.M)` -> ['A','M'] ;
        les kwargs (`metaclass=...`) sont ignorés.
      - JS/TS  : enfant `class_heritage`. En JS ses enfants sont directement les expressions
        `extends` ; en TS on ne prend QUE l'`extends_clause` (les `implements_clause` =
        interfaces, pas d'héritage de méthode) et on saute les `type_arguments` (`Base<T>`).
    `class_heritage` (JS/TS) porte l'héritage de MÉTHODES ; on résout ensuite chaque nom via
    l'index de classes. Bases non nommées / hors repo : simplement ignorées (jamais d'erreur)."""
    if class_node is None:
        return []
    # Python
    superclasses = class_node.child_by_field_name("superclasses")
    if superclasses is not None:
        return [n for n in (_base_name(c) for c in superclasses.named_children) if n]
    # JS/TS
    bases = []
    for child in class_node.named_children:
        if child.type != "class_heritage":
            continue
        for h in child.named_children:
            if h.type == "extends_clause":          # TS
                for e in h.named_children:
                    if e.type == "type_arguments":  # Base<T> : sauter les params de type
                        continue
                    name = _base_name(e)
                    if name:
                        bases.append(name)
            elif h.type == "implements_clause":     # TS : interfaces -> pas d'héritage de méthode
                continue
            else:                                   # JS : enfants directs = expressions extends
                name = _base_name(h)
                if name:
                    bases.append(name)
    return bases


def _clean_sig(raw):
    """Première ligne d'une déf -> signature lisible (sans le ':' Python ou le '{' JS/TS)."""
    s = raw.strip()
    while s.endswith(("{", ":")):
        s = s[:-1].strip()
    return s


def _normalize_import(n):
    """Rend (spec, level) à partir du nœud @reference.import capturé — le TYPE de nœud
    diffère par grammaire (string en JS/TS, dotted_name/relative_import en Python), donc
    on dispatche dessus plutôt que de supposer un format commun.
    level = 0 pour un import absolu (Python 'import x.y', tout JS/TS), > 0 pour un import
    relatif Python (nb de points de tête, ex ".foo" -> level=1, "..pkg" -> level=2)."""
    t = n.type
    text = n.text.decode("utf8")
    if t == "string":
        return text.strip("'\"`"), 0  # JS/TS : guillemets retirés
    if t == "relative_import":
        level = len(text) - len(text.lstrip("."))
        return text[level:], level  # ex ".foo.bar" -> ("foo.bar", 1)
    return text, 0  # dotted_name (import absolu Python)


def parse_file(spec, source):
    """Rend (defs, refs, imports, import_bindings, assignments) pour un fichier, selon la
    spec de langage."""
    tree = spec["parser"].parse(source)
    lines = source.split(b"\n")
    captures = QueryCursor(spec["query"]).captures(tree.root_node)

    # 1) défs fonction/classe : le PARENT du nom porte les bornes (corps complet)
    defs = []
    def_lines = set()  # lignes déjà prises par une fonction/classe (dédup des variables)
    for cap_name, kind in (("definition.function", "function"),
                           ("definition.class", "class")):
        for n in captures.get(cap_name, []):
            parent = n.parent
            sig_line = parent.start_point[0] if parent else n.start_point[0]
            end_line = parent.end_point[0] if parent else n.start_point[0]
            entry = {
                "name": n.text.decode("utf8"),
                "kind": kind,
                "line": sig_line + 1,       # 1re ligne de la déf
                "end_line": end_line + 1,   # dernière ligne du corps (pour get_symbol)
                "signature": _clean_sig(lines[sig_line].decode("utf8", "replace")),
            }
            if kind == "class":
                # classes de base (Python : `class B(A, mixins.M):`) — pour résoudre un
                # self.foo() hérité vers la méthode de la classe mère (cf. assemble). Le
                # champ `superclasses` n'existe que dans la grammaire Python ; en JS/TS il
                # est absent (héritage via class_heritage, hors scope) -> bases = [], sûr.
                entry["bases"] = _class_bases(parent)
            defs.append(entry)
            def_lines.add(sig_line + 1)

    # les fonctions/classes servent de SCOPES pour situer variables et appels (par plage)
    scopes = list(defs)

    # 2) variables/constantes de NIVEAU MODULE seulement (flags type ENABLE_X, alias de
    # type…). On saute les locales (sinon explosion de bruit) et les arrow déjà prises
    # comme fonctions (même ligne -> doublon).
    for n in captures.get("definition.variable", []):
        line0 = n.start_point[0]
        if (line0 + 1) in def_lines:
            continue
        if _enclosing_name(scopes, line0 + 1) != "<module>":
            continue
        defs.append({
            "name": n.text.decode("utf8"),
            "kind": "variable",
            "line": line0 + 1,
            "end_line": line0 + 1,
            "signature": lines[line0].decode("utf8", "replace").strip(),
        })

    # 3) références (appels) : englobant trouvé par plage de lignes
    # récepteur d'un appel d'attribut simple (self/cls/autre), corrélé via l'id du noeud
    # `attribute` PARENT commun aux deux captures — PAS via `is`/`==` sur les objets Node :
    # py-tree-sitter recrée un nouvel objet Node à chaque accès `.parent`, donc comparer les
    # objets eux-mêmes échoue silencieusement (aucune erreur, juste 0 corrélation trouvée).
    receiver_by_parent = {
        n.parent.id: n.text.decode("utf8")
        for n in captures.get("reference.receiver", [])
        if n.parent is not None
    }
    refs = []
    for n in captures.get("reference.call", []):
        line = n.start_point[0] + 1
        parent = n.parent
        receiver = receiver_by_parent.get(parent.id) if parent is not None else None
        refs.append({
            "name": n.text.decode("utf8"),
            "line": line,
            "from": _enclosing_name(scopes, line),
            "receiver": receiver,  # "self" / "cls" / autre identifiant / None
        })

    # 3.5) affectations `x = Ctor(...)` (Python) / `const x = new Ctor(...)` (JS/TS) ->
    # INFÉRENCE DE TYPE : lie une variable à la classe de l'objet qu'on lui assigne, pour
    # résoudre `x.foo()` vers Ctor.foo au lieu d'un fan-out par nom (résolution dans assemble).
    # La capture @typeinfer.assign pointe un nœud de forme DIFFÉRENTE selon la grammaire
    # (assignment Python vs variable_declarator JS/TS) -> on dispatche sur son type, comme
    # _normalize_import. On ne retient que le constructeur SIMPLE (identifiant) : `x = mod.Ctor()`
    # / `new ns.Ctor()` (attribut) et les cibles non-constructeur sont hors scope. Le `scope`
    # (def englobant, comme les refs) sert de clé ; toutes les affectations sont gardées (niveau
    # module inclus), la désambiguïsation (réaffectation à un type différent) se fait dans assemble.
    assignments = []
    for n in captures.get("typeinfer.assign", []):
        if n.type == "assignment":              # Python : x = Ctor(...)
            var_node = n.child_by_field_name("left")
            val = n.child_by_field_name("right")
            type_node = val.child_by_field_name("function") if (
                val is not None and val.type == "call") else None
        elif n.type == "variable_declarator":   # JS/TS : const x = new Ctor(...)
            var_node = n.child_by_field_name("name")
            val = n.child_by_field_name("value")
            type_node = val.child_by_field_name("constructor") if (
                val is not None and val.type == "new_expression") else None
        else:
            continue
        if (var_node is None or type_node is None
                or var_node.type != "identifier" or type_node.type != "identifier"):
            continue
        line = var_node.start_point[0] + 1
        assignments.append({
            "var": var_node.text.decode("utf8"),
            "type": type_node.text.decode("utf8"),
            "scope": _enclosing_name(scopes, line),
        })

    # 4) imports (spec brute, non résolue ici — la résolution dépend des AUTRES fichiers
    # du repo, donc elle se fait dans assemble() une fois tous les fichiers parsés)
    imports = []
    for n in captures.get("reference.import", []):
        spec, level = _normalize_import(n)
        if spec:
            imports.append({"spec": spec, "level": level})

    # 5) bindings de noms importés (Python `from mod import orig as local`) : lie chaque nom
    # LOCAL utilisable comme appel direct `local()` à (module, nom d'origine). Sert dans
    # assemble() à résoudre l'appel vers LE fichier importé au lieu d'un fan-out par nom (et
    # à passer outre le filtre builtin : un nom explicitement importé est forcément interne).
    # `from x import *` (wildcard) et `import x`/`import x as y` (nom de MODULE, pas de symbole
    # directement appelable) sont hors scope ici. JS/TS : pas d'`import_from_statement` -> vide.
    import_bindings = []
    for n in captures.get("reference.import.from", []):
        mod_node = n.child_by_field_name("module_name")
        if mod_node is None:
            continue
        spec, level = _normalize_import(mod_node)
        if not spec and level == 0:
            continue
        for name_node in n.children_by_field_name("name"):
            if name_node.type == "dotted_name":
                local = orig = name_node.text.decode("utf8")
            elif name_node.type == "aliased_import":
                orig_n = name_node.child_by_field_name("name")
                alias_n = name_node.child_by_field_name("alias")
                if orig_n is None or alias_n is None:
                    continue
                orig = orig_n.text.decode("utf8")
                local = alias_n.text.decode("utf8")
            else:
                continue  # wildcard_import, etc.
            import_bindings.append({"local": local, "orig": orig, "spec": spec, "level": level})

    # 6) bindings de MODULE (namespace/default) -> INFÉRENCE sur `ns.foo()` / `Foo()` :
    #  - namespace_bindings : nom_local -> module (fichier) ; usage `ns.foo()` résolu vers
    #    module::foo. JS/TS `import * as ns` + Python `import mod` / `import pkg.mod as m`.
    #  - default_bindings   : nom_local -> export DEFAULT du module (JS/TS `import Foo from ...`) ;
    #    résolu vers le vrai symbole exporté (le nom local peut différer, cf. assemble).
    #  - default_export     : nom du symbole exporté par DÉFAUT de CE fichier (JS/TS), pour
    #    qu'un autre fichier l'important en default résolve vers lui.
    namespace_bindings, default_bindings = [], []
    default_export = None

    # JS/TS : un seul import_statement peut porter les trois formes
    # (`import Foo, { a as b }, * as ns from './mod'`). On dispatche sur le type de clause.
    for n in captures.get("reference.import.stmt", []):
        source = n.child_by_field_name("source")
        if source is None:
            continue
        spec, level = _normalize_import(source)  # string -> guillemets retirés, level 0
        if not spec:
            continue
        for clause in n.named_children:
            if clause.type != "import_clause":
                continue
            for named in clause.named_children:
                if named.type == "named_imports":            # import { orig as local }
                    for isp in named.named_children:
                        if isp.type != "import_specifier":
                            continue
                        name_n = isp.child_by_field_name("name")
                        if name_n is None:
                            continue
                        alias_n = isp.child_by_field_name("alias")
                        orig = name_n.text.decode("utf8")
                        local = alias_n.text.decode("utf8") if alias_n is not None else orig
                        import_bindings.append({"local": local, "orig": orig, "spec": spec, "level": level})
                elif named.type == "namespace_import":        # import * as ns
                    for c in named.named_children:
                        if c.type == "identifier":
                            namespace_bindings.append(
                                {"local": c.text.decode("utf8"), "spec": spec, "level": level})
                elif named.type == "identifier":              # import Foo (default)
                    default_bindings.append(
                        {"local": named.text.decode("utf8"), "spec": spec, "level": level})

    # Python : `import mod` / `import pkg.mod as m` — lie un nom de MODULE (usage `mod.foo()`).
    # Sans alias, seul un module à UN segment (`import mod`) est utilisable comme récepteur
    # simple `mod.foo()` (un `import pkg.mod` s'appelle `pkg.mod.foo()`, récepteur composé non
    # capturé). Avec alias, le local est l'alias et le module = le chemin pointé complet.
    for n in captures.get("reference.import.mod", []):
        for name_node in n.children_by_field_name("name"):
            if name_node.type == "dotted_name":
                if sum(1 for c in name_node.children if c.type == "identifier") != 1:
                    continue  # import pkg.mod (multi-segment, sans alias) -> hors scope
                local = name_node.text.decode("utf8")
                namespace_bindings.append({"local": local, "spec": local, "level": 0})
            elif name_node.type == "aliased_import":          # import pkg.mod as m
                mod_n = name_node.child_by_field_name("name")
                alias_n = name_node.child_by_field_name("alias")
                if mod_n is None or alias_n is None:
                    continue
                namespace_bindings.append({
                    "local": alias_n.text.decode("utf8"),
                    "spec": mod_n.text.decode("utf8"), "level": 0,
                })

    # nom de l'export DEFAULT de ce fichier (JS/TS) : au plus un par fichier.
    for n in captures.get("reference.export.default", []):
        default_export = n.text.decode("utf8")
        break

    mod_imports = {"namespace": namespace_bindings, "default": default_bindings,
                   "default_export": default_export}
    return defs, refs, imports, import_bindings, assignments, mod_imports


def _scan(folder, prev=None):
    """Parse les fichiers SUPPORTÉS du dossier en RÉUTILISANT les inchangés (régé
    incrémentale). `prev` = graphe précédent ({'files':..., 'mtimes':...}) ou None. Un
    fichier est reparsé seulement si son mtime a changé (ou s'il est nouveau) ; les
    supprimés disparaissent. Retourne (files, mtimes, reparsed, reused)."""
    prev_files = (prev or {}).get("files", {})
    prev_mtimes = (prev or {}).get("mtimes", {})
    files, mtimes = {}, {}
    reparsed = reused = 0

    paths = []
    for root, dirs, fnames in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for fn in fnames:
            if fn.endswith((".d.ts", ".min.js")):
                continue  # déclarations de types / bundles minifiés = bruit
            if os.path.splitext(fn)[1].lower() in LANGS:
                paths.append(os.path.join(root, fn))

    for path in sorted(paths):
        rel = os.path.relpath(path, folder).replace("\\", "/")
        try:
            mt = os.path.getmtime(path)
        except OSError:
            continue
        mtimes[rel] = mt
        if rel in prev_files and prev_mtimes.get(rel) == mt:
            files[rel] = prev_files[rel]          # inchangé -> on garde le parse précédent
            reused += 1
        else:
            spec = LANGS[os.path.splitext(path)[1].lower()]
            with open(path, "rb") as fh:
                source = fh.read()
            defs, refs, imports, import_bindings, assignments, mod_imports = parse_file(spec, source)
            files[rel] = {"defs": defs, "refs": refs, "imports": imports,
                          "import_bindings": import_bindings, "assignments": assignments,
                          "mod_imports": mod_imports}
            reparsed += 1
    return files, mtimes, reparsed, reused


def _resolve_py_import(files, current_rel, spec, level):
    """Spec Python -> chemin de fichier CONNU du repo, ou None (approximatif : suppose
    que la racine des imports absolus = le dossier scanné ; repli par suffixe pour un
    layout src/ ou un package installé en editable)."""
    if level > 0:  # relatif : from . import x / from .foo import x / from ..pkg import x
        parts = current_rel.split("/")[:-1]  # dossier du fichier courant
        up = level - 1  # niveau 1 = le paquet courant (le dossier lui-même)
        if up:
            parts = parts[:-up] if up <= len(parts) else []
        base = "/".join(parts)
        path = f"{base}/{spec.replace('.', '/')}".strip("/") if spec else base
    else:  # absolu : import x.y.z / from x.y import z
        path = spec.replace(".", "/")
    # cas "from . import x" au niveau racine du repo : path == "" -> pas de "/" de tête
    init_cand = f"{path}/__init__.py" if path else "__init__.py"
    for cand in filter(None, (f"{path}.py" if path else None, init_cand)):
        if cand in files:
            return cand
    if level == 0:  # repli : matche par SUFFIXE (layout src/, package installé...)
        for f in files:
            stem = f[:-3] if f.endswith(".py") else f
            if stem == path or stem.endswith("/" + path):
                return f
    return None


def _resolve_js_import(files, current_rel, spec):
    """Spec JS/TS -> chemin de fichier CONNU du repo, ou None (paquet npm externe non
    résolu — node_modules est de toute façon exclu du scan)."""
    if not spec.startswith((".", "/")):
        return None
    base_dir = "/".join(current_rel.split("/")[:-1])
    raw = os.path.normpath((base_dir + "/" + spec) if base_dir else spec).replace("\\", "/").lstrip("/")
    if raw in files:
        return raw
    for ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
        if f"{raw}{ext}" in files:
            return f"{raw}{ext}"
    for ext in (".ts", ".tsx", ".js", ".jsx"):
        if f"{raw}/index{ext}" in files:
            return f"{raw}/index{ext}"
    return None


def _resolve_import(files, current_rel, imp):
    """Dispatch par extension du fichier courant (pas de langue stockée par import)."""
    if current_rel.endswith(".py"):
        return _resolve_py_import(files, current_rel, imp["spec"], imp["level"])
    return _resolve_js_import(files, current_rel, imp["spec"])


def _import_edges(files):
    """Graphe FICHIER -> FICHIER (au niveau <module>) construit depuis les imports,
    en PLUS du graphe d'appels — capture la structure (JSX/composants, ré-exports...)
    qui échappe au graphe d'appels pur. Fanout vers TOUTES les défs du fichier importé
    (approximatif : pas de résolution d'exports précise), dilué ensuite par le même
    poids 1/(fan-in) que les appels -> un fichier générique très importé ne domine pas."""
    edges = []
    for rel, data in files.items():
        for imp in data.get("imports", []):
            target = _resolve_import(files, rel, imp)
            if target and target != rel:
                for d in files[target]["defs"]:
                    edges.append([f"{rel}::<module>", f"{target}::{d['name']}"])
    return edges


def rerank(files, edges, import_edges, mentioned=None, touched=None):
    """Calcule le PageRank sur appels + imports FUSIONNÉS, avec en PLUS une pondération
    CONTEXTUELLE façon Aider (repomap.py : mul *= 10 pour un identifiant mentionné,
    mul *= 50 pour un fichier en cours de consultation) — recalculé À LA DEMANDE (pas mis
    en cache disque, car dépend du contexte de SESSION, pas du code) :
      - `mentioned` (identifiants explicitement demandés dans la session : where_is/
        get_symbol/who_references) -> 10x sur les arêtes dont la CIBLE porte ce nom
        (ce qu'on demande explicitement doit remonter).
      - `touched` (fichiers consultés récemment : outline/get_symbol) -> 50x sur les
        arêtes dont la SOURCE est un de ces fichiers (ce qu'on regarde en ce moment
        rend ses propres références plus significatives).
    Rend {"file::name" -> rank}, ne mute rien. Pas de reprise du 0.1x d'Aider sur les
    symboles privés/multi-définis : notre dilution 1/fan-in (ci-dessous) sert déjà ce
    rôle anti-ubiquitaire par un mécanisme différent -> pas dupliqué pour éviter deux
    heuristiques qui se marchent dessus.

    ⚠ Le poids final est PLAFONNÉ à 1.0 (min(1.0, ...)) — pagerank.py (voir son docstring)
    traite le poids comme un facteur d'ABSORPTION ∈ (0,1], PAS un boost multiplicatif libre :
    sans ce plafond, un symbole à la fois mentionné (10x) ET référencé depuis un fichier
    touché (50x -> 500x cumulé) peut faire DIVERGER l'itération (rang > 50 observé en test,
    hors de toute échelle sensée ~0.0001-0.01) — le poids > 1 casse l'hypothèse de
    convergence sous-stochastique du modèle. Le plafond borne le boost à « absorption
    complète de cette arête », jamais plus, quel que soit le nombre de facteurs cumulés."""
    mentioned = mentioned or set()
    touched = touched or set()
    all_edges = edges + import_edges

    def ctx_mul(caller, callee):
        mul = 1.0
        if callee.split("::", 1)[1] in mentioned:
            mul *= 10.0
        if caller.split("::", 1)[0] in touched:
            mul *= 50.0
        return mul

    # Sous-pondération des UBIQUITAIRES (anti faux-n°1 type `_trace`/log/`flush`) : une arête
    # vers un symbole appelé depuis BEAUCOUP d'appelants distincts est un signal FAIBLE
    # (générique) ; vers un symbole appelé depuis peu d'endroits = signal FORT (spécifique).
    # Poids = 1/(fan-in distinct) : un symbole appelé depuis N endroits ne fait absorber que
    # 1/N à chacun -> neutralise la pure popularité (un log appelé partout retombe), on garde
    # « appelé PAR du code important ». Testé sur cerveau-viz (_trace n.1 -> n.14) + click
    # (sort flush/write/fileno du top). Exposant 1.0 retenu après comparaison 0.5/0.75/1.0.
    # S'applique pareil aux arêtes d'import (même dilution anti-popularité-brute) : fan-in
    # calculé sur l'UNION appels+imports, un composant importé par 50 fichiers ne domine pas.
    # Le multiplicateur contextuel se compose PAR-DESSUS cette dilution (comme Aider compose
    # ses propres mul *=), pas à la place.
    callers_of = defaultdict(set)
    for caller, callee in all_edges:
        callers_of[callee].add(caller)
    weighted = [(caller, callee, min(1.0, ctx_mul(caller, callee) / len(callers_of[callee])))
                for caller, callee in all_edges]

    return pagerank(weighted)


def apply_ranks(files, symbols, ranks):
    """Annote defs/symbols du rank donné (MUTATION en place) — pour les consommateurs
    qui veulent un graphe 'figé' sans contexte de session (CLI, viz standalone), par
    opposition à server.py qui appelle `rerank` à la volée par session sans jamais le
    graver dans le cache disque (cf. docstring de `rerank`)."""
    for rel, data in files.items():
        for d in data["defs"]:
            d["rank"] = round(ranks.get(f"{rel}::{d['name']}", 0.0), 6)
    for name, entries in symbols.items():
        for e in entries:
            e["rank"] = round(ranks.get(f"{e['file']}::{name}", 0.0), 6)


def _resolve_method(files, classes, class_index, class_key, method_name, visited):
    """Résout `method_name` en partant de la classe `class_key` (=(file, line)) puis en
    REMONTANT ses classes de base (héritage). Rend (file, method_name) de la 1re classe de
    la hiérarchie qui définit la méthode, ou None. Les bases sont résolues PAR NOM via
    `class_index` (pas de suivi d'import) : une base hors repo, ou dont le nom ne matche
    aucune classe indexée, est simplement ignorée. `visited` casse les cycles d'héritage.
    Ordre : classe elle-même d'abord, puis bases dans l'ordre de déclaration (approx. MRO
    suffisante ici — on s'arrête au 1er hit)."""
    if class_key in visited:
        return None
    visited.add(class_key)
    entry = classes.get(class_key)
    if entry is None:
        return None
    cfile, cdef = entry
    for d in files[cfile]["defs"]:
        if (d["kind"] == "function" and d["name"] == method_name
                and cdef["line"] <= d["line"] <= cdef["end_line"]):
            return (cfile, method_name)
    for base in cdef.get("bases", []):
        # imports non suivis -> un nom de base peut matcher plusieurs classes homonymes de
        # fichiers différents. Heuristique : préférer la classe de base du MÊME fichier que
        # la classe dérivée (cas de loin le plus fréquent, et le plus sûr sans résoudre les
        # imports). `k[0] != cfile` -> 0 (même fichier) trié avant 1 (autres), tri stable.
        candidates = sorted(class_index.get(base, []), key=lambda k: k[0] != cfile)
        for bkey in candidates:
            hit = _resolve_method(files, classes, class_index, bkey, method_name, visited)
            if hit is not None:
                return hit
    return None


def assemble(files):
    """À partir des {fichier: {defs, refs, imports}}, (re)calcule l'index `symbols`, les
    `edges` d'APPELS (exposés à who_references, résolus par NOM, builtins exclus) et le
    graphe `import_edges` (résolu, mais gardé SÉPARÉ — jamais dans `edges`, pour ne pas
    polluer who_references de faux positifs "importe mais n'appelle jamais"). Le PageRank
    n'est PLUS calculé ici : il dépend du contexte de session (cf. `rerank`), donc il est
    recalculé à la demande par server.py, pas mis en cache disque avec le graphe statique.
    Recalculé intégralement à chaque fois — négligeable même sur gros repo."""
    # index global nom -> [ {file, line, kind} ]  (pour where_is + résolution)
    symbols = {}
    for rel, data in files.items():
        for d in data["defs"]:
            symbols.setdefault(d["name"], []).append(
                {"file": rel, "line": d["line"], "kind": d["kind"]}
            )

    # registres de classes pour la résolution d'héritage (self.foo() hérité) :
    #  - classes      : (file, line) -> (file, class_def)   accès direct par clé de scope
    #  - class_index  : nom de classe -> [ (file, line) ]   pour résoudre un nom de base
    classes, class_index = {}, {}
    for rel, data in files.items():
        for d in data["defs"]:
            if d["kind"] == "class":
                key = (rel, d["line"])
                classes[key] = (rel, d)
                class_index.setdefault(d["name"], []).append(key)

    # résolution des imports NOMMÉS (Python `from mod import orig as local`) : par fichier,
    # nom_local -> (fichier_cible, nom_d_origine). Sert à résoudre un appel direct `local()`
    # vers LE fichier importé au lieu d'un fan-out par nom, et à passer outre le filtre
    # builtin. On ne garde le binding QUE si le fichier cible définit vraiment le nom
    # d'origine (sinon ré-export/indirection non suivie -> repli par nom, jamais d'arête
    # inventée vers un fichier qui ne définit pas le symbole).
    import_targets = {}
    for rel, data in files.items():
        bmap = {}
        for b in data.get("import_bindings", []):
            target = _resolve_import(files, rel, {"spec": b["spec"], "level": b["level"]})
            if target is None:
                continue
            if any(d["name"] == b["orig"] for d in files[target]["defs"]):
                bmap[b["local"]] = (target, b["orig"])
        if bmap:
            import_targets[rel] = bmap

    # INFÉRENCE DE TYPE : par fichier, {scope: {variable: nom_de_classe}} depuis les
    # affectations `x = Ctor(...)`. Sert à résoudre `x.foo()` vers la classe de x (précis)
    # au lieu du fan-out par nom. PRUDENCE (préserve l'invariant "jamais d'arête perdue") :
    # si une variable est réaffectée à un type DIFFÉRENT dans le même scope, on la marque
    # ambiguë (None) et on n'infère pas -> repli fan-out. Pas de flow-sensitivity (l'ordre
    # des affectations est ignoré) : on ne cherche que le cas non-ambigu, sûr.
    var_types = {}
    for rel, data in files.items():
        per_scope = {}
        for a in data.get("assignments", []):
            d = per_scope.setdefault(a["scope"], {})
            if a["var"] in d and d[a["var"]] != a["type"]:
                d[a["var"]] = None            # réaffectation à un type différent -> ambigu
            elif a["var"] not in d:
                d[a["var"]] = a["type"]
        if per_scope:
            var_types[rel] = per_scope

    # RÉSOLUTION DES IMPORTS DE MODULE (namespace/default) — même prudence qu'import_targets
    # (jamais d'arête inventée : on ne garde un binding que si sa cible existe vraiment) :
    #  - namespace_targets[fichier] = {local: fichier_module}      -> `ns.foo()` = module::foo
    #  - default_targets[fichier]   = {local: (fichier, nom_réel)} -> `import Foo` (default) résout
    #    vers LE symbole exporté par défaut du module (nom local possiblement ≠ nom du symbole).
    default_export_of = {rel: data.get("mod_imports", {}).get("default_export")
                         for rel, data in files.items()}
    namespace_targets, default_targets = {}, {}
    for rel, data in files.items():
        mi = data.get("mod_imports", {})
        nmap = {}
        for b in mi.get("namespace", []):
            target = _resolve_import(files, rel, {"spec": b["spec"], "level": b["level"]})
            if target is not None:
                nmap[b["local"]] = target
        if nmap:
            namespace_targets[rel] = nmap
        dmap = {}
        for b in mi.get("default", []):
            target = _resolve_import(files, rel, {"spec": b["spec"], "level": b["level"]})
            if target is None:
                continue
            real = default_export_of.get(target)
            if real and any(d["name"] == real for d in files[target]["defs"]):
                dmap[b["local"]] = (target, real)
        if dmap:
            default_targets[rel] = dmap

    # arêtes du graphe : (symbole appelant) -> (symbole défini), résolues par NOM
    # (sauf self./cls. ci-dessous, résolus par SCOPE quand la classe englobante est connue)
    edges = []
    for rel, data in files.items():
        for r in data["refs"]:
            caller = f"{rel}::{r['from']}"
            if r.get("receiver") in SELF_RECEIVERS:
                # self.list()/self.parse()/this.map() ne peuvent JAMAIS désigner le builtin/la méthode
                # ubiquitaire homonyme d'un AUTRE langage -> pas de filtre ALL_BUILTINS ici
                # (c'est justement ce filtre, appliqué aveuglément à tout appel, qui faisait
                # disparaître ces méthodes du graphe avant cette résolution par scope).
                cls_def = _enclosing_class(data["defs"], r["line"])
                resolved = None
                if cls_def is not None:
                    # résout dans la classe englobante PUIS en remontant ses classes de base
                    # (héritage). La méthode héritée peut vivre dans un AUTRE fichier -> la
                    # cible de l'arête est le fichier de la classe qui la définit réellement.
                    resolved = _resolve_method(files, classes, class_index,
                                               (rel, cls_def["line"]), r["name"], set())
                if resolved is not None:
                    # résolution précise : UNE arête, vers LA méthode de la classe (propre ou
                    # héritée) — pas de fan-out vers des homonymes d'autres classes sans rapport.
                    rfile, rname = resolved
                    edges.append([caller, f"{rfile}::{rname}"])
                elif r["name"] in symbols:
                    # repli (héritage/mixin hors scope de cette résolution, cf. plan) :
                    # comportement d'avant, SANS filtre builtin puisqu'on sait que c'est un
                    # appel de méthode. Assumé : peut créer des arêtes vers une fonction libre
                    # homonyme si aucune méthode de ce nom n'existe nulle part dans le repo —
                    # jamais de PERTE d'arête par rapport à avant, mais peut en AJOUTER.
                    for target in symbols[r["name"]]:
                        edges.append([caller, f"{target['file']}::{r['name']}"])
                continue
            # appel de méthode `x.foo()` sur une variable de type INFÉRÉ (x = Ctor(...)) :
            # résout précisément vers la méthode de Ctor (propre ou héritée) au lieu du fan-out
            # par nom. Prudent : seulement si le type est connu, NON ambigu (une seule classe de
            # ce nom) et si la méthode s'y résout ; sinon on laisse le fan-out ci-dessous
            # (jamais de PERTE d'arête — au pire on retombe sur le comportement d'avant).
            receiver = r.get("receiver")
            if receiver is not None:
                # (a) x.foo() sur variable de type inféré (x = Ctor() / const x = new Ctor())
                tname = var_types.get(rel, {}).get(r["from"], {}).get(receiver)
                if tname is not None:
                    cls_keys = class_index.get(tname, [])
                    if not cls_keys:
                        # le type inféré peut être un import DEFAULT (`const x = new M()`, M =
                        # default d'un module = une classe de nom différent) -> suivre le binding.
                        dflt = default_targets.get(rel, {}).get(tname)
                        if dflt is not None:
                            tfile, real = dflt
                            cls_keys = [k for k in class_index.get(real, []) if k[0] == tfile]
                    if len(cls_keys) == 1:
                        resolved = _resolve_method(files, classes, class_index,
                                                   cls_keys[0], r["name"], set())
                        if resolved is not None:
                            rfile, rname = resolved
                            edges.append([caller, f"{rfile}::{rname}"])
                            continue
                # (b) ns.foo() où ns lie un MODULE (import * as ns / import mod) -> module::foo.
                # Prudent comme import_targets : arête SEULEMENT si le module définit le nom ;
                # sinon (ré-export non suivi, membre d'objet) on retombe sur le fan-out ci-dessous.
                nmap = namespace_targets.get(rel)
                if nmap is not None and receiver in nmap:
                    tfile = nmap[receiver]
                    if any(d["name"] == r["name"] for d in files[tfile]["defs"]):
                        edges.append([caller, f"{tfile}::{r['name']}"])
                        continue
            # appel direct `foo()` : un nom explicitement importé (`from mod import foo`)
            # résout DIRECTEMENT vers le fichier importé — AVANT le filtre builtin (un nom
            # importé est forcément interne, même s'il s'appelle comme un builtin) et sans
            # fan-out vers les homonymes des autres fichiers.
            bmap = import_targets.get(rel)
            if bmap is not None and r["name"] in bmap:
                tfile, torig = bmap[r["name"]]
                edges.append([caller, f"{tfile}::{torig}"])
                continue
            dmap = default_targets.get(rel)
            if dmap is not None and r["name"] in dmap:
                # `Foo()` où Foo = import default d'un module -> LE symbole exporté par défaut
                # (nom réel possiblement ≠ Foo). Comme import_targets : avant le filtre builtin.
                tfile, real = dmap[r["name"]]
                edges.append([caller, f"{tfile}::{real}"])
                continue
            if r["name"] in ALL_BUILTINS:  # appel d'un builtin -> pas une arête interne
                continue
            if r["name"] in symbols:  # on ne garde que les appels internes au repo
                for target in symbols[r["name"]]:
                    callee = f"{target['file']}::{r['name']}"
                    edges.append([caller, callee])

    # Graphe d'imports (fichier -> fichier), calculé UNIQUEMENT pour muscler le ranking —
    # cf. limite mesurée le 29/06 : sur du JSX/React, la structure passe par la composition
    # de composants (imports), pas par des appels de fonction, donc le call-graph seul rate
    # les vrais organes. Gardé séparé de `edges` (jamais fusionné dedans), fusionné seulement
    # au moment du ranking dans `rerank`.
    import_edges = _import_edges(files)

    return {"files": files, "symbols": symbols, "edges": edges, "import_edges": import_edges}


def build(folder, prev=None):
    """Construit le graphe. Si `prev` est fourni, build INCRÉMENTAL (ne reparse que ce qui
    a changé). Le résultat embarque `mtimes` (pour le prochain incrément) et `_stats`.
    Ne contient PAS de rank calculé (cf. `rerank`, dépendant du contexte de session)."""
    files, mtimes, reparsed, reused = _scan(folder, prev)
    graph = assemble(files)
    graph["mtimes"] = mtimes
    graph["_schema"] = SCHEMA_VERSION
    graph["_stats"] = {"reparsed": reparsed, "reused": reused,
                        "import_edges": len(graph["import_edges"])}
    return graph


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("-o", "--out", default="code_graph.json")
    args = ap.parse_args()

    graph = build(args.folder)
    # CLI/fichier statique -> rank SANS contexte de session (neutre), figé dans le JSON
    # (contrairement à server.py, qui appelle rerank() à la volée par session).
    ranks = rerank(graph["files"], graph["edges"], graph["import_edges"])
    apply_ranks(graph["files"], graph["symbols"], ranks)
    with open(args.out, "w", encoding="utf8") as fh:
        json.dump(graph, fh, ensure_ascii=False, indent=2)

    n_defs = sum(len(d["defs"]) for d in graph["files"].values())
    n_refs = sum(len(d["refs"]) for d in graph["files"].values())
    n_imports = graph["_stats"].get("import_edges", 0)
    print(f"{len(graph['files'])} fichiers | {n_defs} définitions | "
          f"{n_refs} références | {len(graph['edges'])} arêtes internes (appels) | "
          f"{n_imports} arêtes d'import (ranking seulement)")
    print(f"-> {args.out}")
