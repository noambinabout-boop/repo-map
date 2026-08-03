"""server.py — serveur MCP "repo-map".

La FAÇADE : expose à Claude Code 6 outils déterministes pour s'orienter dans un
repo SANS lire les fichiers entiers. Tout vient de code_graph.json (construit par
build_graph.py), sauf get_symbol qui va chercher le corps réel à la demande.

Outils :
  index(path)            -> (re)cible le serveur sur N'IMPORTE QUEL dossier
  outline(file)          -> signatures du fichier (table des matières)
  where_is(query)        -> où est défini un symbole, top 5 triés par PageRank CONTEXTUEL
  grep_code(pattern)     -> recherche par contenu, situé dans son symbole englobant
  get_symbol(file, name) -> le corps d'UN symbole seulement
  who_references(name)    -> qui appelle ce symbole (impact d'un changement)

Cible (TARGET) :
  - par défaut = le dossier où Claude Code est ouvert (cwd du process).
  - surchargeable au lancement par REPO_MAP_TARGET.
  - changeable à la volée par l'outil index(path) -> usage "global" : on installe
    le serveur une fois (user-scope) et on le pointe sur le projet voulu, même
    depuis le vault.

Build LAZY : le graphe n'est construit qu'au premier outil utilisé (ou à index),
jamais au démarrage -> on peut l'installer global sans scanner un gros dossier au boot.

Ranking CONTEXTUEL (façon Aider repomap.py) : le PageRank de where_is n'est PAS figé au
build, il est recalculé À CHAQUE APPEL à partir d'un état de SESSION léger (SESSION,
ci-dessous) — les derniers fichiers consultés (outline/get_symbol) et les derniers
identifiants explicitement demandés (where_is/get_symbol/who_references) reçoivent un
boost multiplicatif avant le PageRank (cf. build_graph.rerank). Le ranking s'adapte donc
à ce sur quoi Claude travaille EN CE MOMENT, pas seulement à la structure statique du code.
"""
import os
import re
import json
import hashlib
from collections import OrderedDict

from mcp.server.fastmcp import FastMCP

from build_graph import build, rerank, SCHEMA_VERSION

mcp = FastMCP("repo-map")

# état mutable : cible courante + graphe (None = pas encore construit)
STATE = {
    "target": os.path.abspath(os.environ.get("REPO_MAP_TARGET") or os.getcwd()),
    "graph": None,
}

# Contexte de SESSION (léger, en mémoire, PAS persisté au cache disque — cf. docstring
# de rerank : le ranking contextuel dépend de ce qu'on regarde MAINTENANT, pas du code).
# OrderedDict utilisé comme un set LRU : la clé la plus récemment touchée passe en fin,
# et on ne garde que les CAP dernières (une session ne doit pas accumuler indéfiniment).
SESSION = {"touched_files": OrderedDict(), "mentioned": OrderedDict()}
TOUCHED_CAP = 8
MENTIONED_CAP = 15


def _touch(bucket, key, cap):
    """Marque `key` comme récemment utilisée dans `bucket` (LRU borné à `cap`)."""
    if not key:
        return
    if key in bucket:
        bucket.move_to_end(key)
    else:
        bucket[key] = None
        if len(bucket) > cap:
            bucket.popitem(last=False)


# Cache CENTRAL (hors des repos ciblés) : un fichier par projet, clé = hash du chemin.
# Surchargeable par REPO_MAP_CACHE. Permet la régé incrémentale entre sessions.
CACHE_DIR = os.environ.get(
    "REPO_MAP_CACHE", os.path.join(os.path.expanduser("~"), ".repo-map", "cache")
)


def _cache_path(target):
    key = hashlib.sha1(os.path.abspath(target).lower().encode("utf8")).hexdigest()[:16]
    return os.path.join(CACHE_DIR, f"{key}.json")


def _load(target):
    """Charge le graphe de `target` en RÉUTILISANT le cache (régé incrémentale : seuls les
    fichiers au mtime changé sont reparsés), repersiste le cache, met à jour STATE."""
    target = os.path.abspath(target)
    path = _cache_path(target)
    prev = None
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf8") as f:
                prev = json.load(f)
        except (OSError, json.JSONDecodeError):
            prev = None  # cache illisible -> rebuild complet
        if prev is not None and prev.get("_schema") != SCHEMA_VERSION:
            prev = None  # schéma de cache périmé (ex: ajout du champ "imports") -> rebuild complet
    graph = build(target, prev)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf8") as f:
        json.dump(graph, f, ensure_ascii=False)
    STATE["target"] = target
    STATE["graph"] = graph
    return graph


def _graph():
    """Graphe courant, construit à la demande la 1re fois."""
    if STATE["graph"] is None:
        _load(STATE["target"])
    return STATE["graph"]


def _ranks():
    """PageRank recalculé À LA DEMANDE avec le contexte de SESSION courant (cf. docstring
    module + build_graph.rerank). Pas cher (quelques milliers d'arêtes, 40 itérations) ->
    recalculer à chaque appel plutôt que de risquer un ranking périmé."""
    graph = _graph()
    return rerank(graph["files"], graph["edges"], graph["import_edges"],
                  mentioned=set(SESSION["mentioned"]), touched=set(SESSION["touched_files"]))


def _enclosing_def(defs, line):
    """Nom du symbole (def/class) dont la plage contient `line`, le plus imbriqué.
    '<module>' si la ligne est au niveau module. Sert à situer un hit de grep_code."""
    best = None
    for d in defs:
        if d["kind"] == "variable":
            continue  # une variable n'englobe rien
        if d["line"] <= line <= d["end_line"]:
            if best is None or (d["end_line"] - d["line"]) < (best["end_line"] - best["line"]):
                best = d
    return best["name"] if best else "<module>"


@mcp.tool()
def index(path: str) -> str:
    """(Re)cible le serveur sur un dossier de code et construit sa carte.
    À appeler EN PREMIER quand tu veux analyser un projet précis (utile depuis un
    autre dossier que le projet). Tous les autres outils opèrent ensuite sur ce dossier."""
    if not os.path.isdir(path):
        return f"Dossier introuvable : {path}"
    SESSION["touched_files"].clear()
    SESSION["mentioned"].clear()  # nouvelle cible -> le contexte de session précédent est périmé
    graph = _load(path)
    n_files = len(graph["files"])
    n_defs = sum(len(d["defs"]) for d in graph["files"].values())
    n_edges = len(graph["edges"])
    if n_defs == 0:
        return (f"Ciblé sur {STATE['target']}, mais 0 définition trouvée. "
                f"repo-map indexe Python, JavaScript/JSX et TypeScript/TSX "
                f"(pas de fichier de code exploitable ici ?).")
    st = graph.get("_stats", {})
    cache = (f" [cache : {st.get('reused', 0)} réutilisés, {st.get('reparsed', 0)} reparsés]"
             if st.get("reused") else " [build complet]")
    return (f"Ciblé sur {STATE['target']} : {n_files} fichiers, {n_defs} définitions, "
            f"{n_edges} arêtes internes.{cache} "
            f"Outils prêts (outline / where_is / grep_code / get_symbol / who_references).")


@mcp.tool()
def outline(file: str) -> str:
    """Table des matières d'un fichier : signatures des classes/fonctions + lignes.
    À utiliser AVANT de lire un fichier : ~95 % moins de tokens qu'un Read complet."""
    graph = _graph()
    data = graph["files"].get(file)
    if data is None:
        files = sorted(graph["files"])
        if not files:
            return (f"Aucun fichier de code indexé. Cible actuelle : {STATE['target']}. "
                    f"Si ce n'est pas le bon projet, appelle index(<dossier>) d'abord "
                    f"(repo-map indexe Python, JS/JSX et TS/TSX).")
        return (f"Fichier inconnu : {file}. Cible : {STATE['target']}. "
                f"Fichiers indexés : {', '.join(files)}")
    _touch(SESSION["touched_files"], file, TOUCHED_CAP)
    if not data["defs"]:
        return f"{file} : aucune définition (fichier de données/constantes ?)."
    out = [f"# Outline {file}"]
    for d in sorted(data["defs"], key=lambda x: x["line"]):
        out.append(f"  {d['signature']}  (L{d['line']}-{d['end_line']})")
    return "\n".join(out)


@mcp.tool()
def where_is(query: str) -> str:
    """Où est défini un symbole ? Recherche par nom (sous-chaîne, insensible à la casse),
    triée par importance PageRank CONTEXTUEL (boosté par les fichiers consultés et les
    identifiants demandés récemment dans la session). Rend les meilleurs candidats avec
    fichier:ligne."""
    graph = _graph()
    q = query.lower()
    matched_names = [name for name in graph["symbols"] if q in name.lower()]
    if not matched_names:
        n = len(graph["symbols"])
        return (f"Aucun symbole ne correspond à « {query} ». "
                f"Cible actuelle : {STATE['target']} ({n} symboles indexés). "
                f"Si ce n'est pas le bon projet, appelle index(<dossier>).")
    ranks = _ranks()
    hits = [(ranks.get(f"{e['file']}::{name}", 0.0), name, e)
            for name in matched_names for e in graph["symbols"][name]]
    hits.sort(key=lambda h: (h[0], h[1]), reverse=True)  # clé (rang, nom) : ne compare jamais le dict `e`
    for _, name, _e in hits[:5]:
        _touch(SESSION["mentioned"], name, MENTIONED_CAP)  # ce qu'on demande explicitement
    out = [f"# where_is(\"{query}\") — {len(hits)} résultat(s), triés par importance"]
    for rank, name, e in hits[:5]:
        out.append(f"  {name}  →  {e['file']}:{e['line']}  ({e['kind']}, rang {rank:.4f})")
    return "\n".join(out)


@mcp.tool()
def grep_code(pattern: str, max_results: int = 40) -> str:
    """Recherche par CONTENU (regex) dans le code indexé, chaque résultat SITUÉ dans son
    symbole englobant (def/class/<module>). Complément de where_is (qui ne cherche que par
    NOM de symbole) : à utiliser pour trouver un littéral, un flag (ENABLE_X), un fragment
    de code, une chaîne — là où un nom de symbole ne suffit pas. Rend « fichier → symbole
    (Ln) : ligne », ce qui situe le hit au lieu d'une ligne nue."""
    graph = _graph()
    try:
        rx = re.compile(pattern)
    except re.error as e:
        return f"Regex invalide : {e}"
    out = []
    n = 0
    for rel in sorted(graph["files"]):
        path = os.path.join(STATE["target"], rel)
        try:
            with open(path, "r", encoding="utf8", errors="replace") as fh:
                lines = fh.readlines()
        except OSError:
            continue
        defs = graph["files"][rel]["defs"]
        for i, line in enumerate(lines, start=1):
            if rx.search(line):
                sym = _enclosing_def(defs, i)
                out.append(f"  {rel} → {sym} (L{i}):  {line.strip()}")
                n += 1
                if n >= max_results:
                    out.append(f"  … (coupé à {max_results} ; affine le motif)")
                    return f"# grep_code(/{pattern}/) — {n}+ résultats\n" + "\n".join(out)
    if not n:
        return (f"Aucune correspondance pour /{pattern}/ dans {STATE['target']} "
                f"(fichiers Python / JS / TS indexés).")
    return f"# grep_code(/{pattern}/) — {n} résultat(s)\n" + "\n".join(out)


@mcp.tool()
def get_symbol(file: str, name: str) -> str:
    """Le corps complet d'UN symbole (par plage de lignes). À n'appeler que pour le(s)
    symbole(s) sur lesquels tu vas réellement coder, jamais pour t'orienter."""
    graph = _graph()
    data = graph["files"].get(file)
    if data is None:
        return f"Fichier inconnu : {file}"
    target = next((d for d in data["defs"] if d["name"] == name), None)
    if target is None:
        names = ", ".join(d["name"] for d in data["defs"])
        return f"Symbole « {name} » absent de {file}. Présents : {names}"
    _touch(SESSION["touched_files"], file, TOUCHED_CAP)
    _touch(SESSION["mentioned"], name, MENTIONED_CAP)
    path = os.path.join(STATE["target"], file)
    with open(path, "r", encoding="utf8", errors="replace") as fh:
        lines = fh.readlines()
    body = lines[target["line"] - 1: target["end_line"]]
    return f"# {file}:{target['line']}-{target['end_line']}\n" + "".join(body)


@mcp.tool()
def who_references(name: str) -> str:
    """Qui appelle ce symbole ? Lecture inverse du graphe = impact d'un changement.
    Indispensable avant de modifier une signature : montre ce qui peut casser."""
    graph = _graph()
    _touch(SESSION["mentioned"], name, MENTIONED_CAP)
    callers = set()
    for src, dst in graph["edges"]:
        if dst.endswith(f"::{name}"):
            callers.add(src)
    callers.discard(f"::{name}")  # auto-référence éventuelle
    real = sorted(c for c in callers if not c.endswith("::<module>"))
    module_level = sorted(c for c in callers if c.endswith("::<module>"))
    if not callers:
        return f"Aucun appel interne à « {name} » (symbole feuille, ou appelé hors repo)."
    out = [f"# who_references(\"{name}\") — {len(callers)} appelant(s)"]
    for c in real:
        out.append(f"  {c.replace('::', '  ::  ')}")
    for c in module_level:
        out.append(f"  {c.split('::')[0]}  (niveau module)")
    return "\n".join(out)


def _starts_for(graph, name):
    """Nœuds de départ correspondant à `name`.

    Trois formes acceptées : un symbole (« maFonction »), un fichier
    (« src/app/page.tsx » → son niveau module) ou un nœud exact
    (« src/app/page.tsx::Home ») pour lever une ambiguïté.
    """
    if "::" in name:
        return [name]
    if name in graph["files"]:
        # Un fichier n'a pas d'appel sortant au niveau module : partir du module
        # SEUL ne donnerait que ses imports. On part donc de tout ce qu'il définit.
        defs = graph["files"][name].get("defs", [])
        return [f"{name}::<module>"] + sorted(f"{name}::{d['name']}" for d in defs)
    starts = set()
    for src, dst in graph["edges"]:
        for node in (src, dst):
            if node.endswith(f"::{name}"):
                starts.add(node)
    return sorted(starts)


def _uses(edges, starts, depth=1):
    """Parcours DESCENDANT du graphe : rend un niveau de nœuds par cran de distance.

    `depth=0` = illimité (fermeture transitive complète). Les cycles sont coupés :
    un nœud déjà vu n'est jamais re-parcouru.
    """
    outgoing = {}
    for src, dst in edges:
        outgoing.setdefault(src, set()).add(dst)
    seen = set(starts)
    frontier = set(starts)
    levels = []
    while frontier and (depth == 0 or len(levels) < depth):
        nxt = set()
        for node in frontier:
            for dst in outgoing.get(node, ()):
                if dst not in seen:
                    seen.add(dst)
                    nxt.add(dst)
        if not nxt:
            break
        levels.append(nxt)
        frontier = nxt
    return levels


def _group_by_file(nodes):
    """« fichier::symbole » -> {fichier: [symboles triés]}, pour un rendu compact."""
    grouped = {}
    for node in nodes:
        file, _, symbol = node.rpartition("::")
        grouped.setdefault(file, []).append(symbol)
    return {f: sorted(s) for f, s in sorted(grouped.items())}


@mcp.tool()
def what_it_uses(name: str, depth: int = 1, max_results: int = 60) -> str:
    """Qu'utilise ce symbole ? Lecture DESCENDANTE du graphe — miroir de who_references.

    who_references remonte (qui m'appelle = ce que je casse) ; celui-ci descend
    (ce dont je dépends = ce que je dois comprendre pour lire ce code).
    Accepte un symbole, un fichier (= tout ce que ce fichier tire) ou un
    « fichier::symbole » exact. `depth=0` donne la fermeture complète : tout le
    code réellement atteint depuis ce point d'entrée.
    """
    graph = _graph()
    _touch(SESSION["mentioned"], name, MENTIONED_CAP)
    starts = _starts_for(graph, name)
    if not starts:
        return f"Symbole ou fichier inconnu : « {name} »."
    # Les deux familles d'arêtes comptent : les appels (symbole -> symbole) et les
    # imports (module -> symbole importé). Les secondes seules portent ce qu'un
    # fichier tire à son niveau module.
    levels = _uses(graph["edges"] + graph["import_edges"], starts, depth)
    total = sum(len(l) for l in levels)
    if not total:
        return (f"« {name} » n'utilise aucun symbole interne "
                f"(feuille du graphe, ou n'appelle que du code hors repo).")

    depth_label = "complet" if depth == 0 else f"profondeur {depth}"
    out = [f"# what_it_uses(\"{name}\", {depth_label}) — {total} symbole(s) "
           f"sur {len(levels)} niveau(x)"]
    if name in graph["files"]:
        out.append(f"  (départ : tout ce que {name} définit et importe)")
    elif len(starts) > 1:
        out.append(f"  (départ ambigu : {len(starts)} définitions de « {name} »)")
    shown = 0
    for i, level in enumerate(levels, 1):
        if shown >= max_results:
            restant = sum(len(l) for l in levels[i - 1:])
            out.append(f"  … {restant} symbole(s) au-delà du niveau {i - 1} "
                       f"(augmenter max_results)")
            break
        out.append(f"  niveau {i} ({len(level)})")
        for file, symbols in _group_by_file(level).items():
            if shown >= max_results:
                break
            visible = symbols[: max_results - shown]
            shown += len(visible)
            suffix = "" if len(visible) == len(symbols) else f" … +{len(symbols) - len(visible)}"
            out.append(f"    {file}  ::  {', '.join(visible)}{suffix}")
    return "\n".join(out)


if __name__ == "__main__":
    mcp.run()
