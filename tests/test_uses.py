"""Tests du parcours descendant (`what_it_uses`).

Autonome, sans dépendance : `python tests/test_uses.py`.
Les cas 1-5 tournent sur un graphe factice (aucun parsing) ; le cas 6 vérifie
que le point d'entrée d'un fichier réel se résout bien.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import _group_by_file, _starts_for, _uses  # noqa: E402

# a::<module> -> a::f -> b::g -> c::h
#                a::f -> b::i
#                       cycle b::g -> a::f
EDGES = [
    ["a.py::<module>", "a.py::f"],
    ["a.py::f", "b.py::g"],
    ["a.py::f", "b.py::i"],
    ["b.py::g", "c.py::h"],
    ["b.py::g", "a.py::f"],
]

echecs = []


def verifie(titre, obtenu, attendu):
    if obtenu != attendu:
        echecs.append(f"{titre}\n    attendu : {attendu}\n    obtenu  : {obtenu}")


# 1. un cran = les voisins directs, rien de plus
verifie("profondeur 1", _uses(EDGES, ["a.py::f"], 1), [{"b.py::g", "b.py::i"}])

# 2. deux crans = le niveau suivant, sans répéter ce qui est déjà vu
verifie("profondeur 2", _uses(EDGES, ["a.py::f"], 2),
        [{"b.py::g", "b.py::i"}, {"c.py::h"}])

# 3. fermeture complète : s'arrête d'elle-même, le cycle ne boucle pas
verifie("profondeur 0 (complète)", _uses(EDGES, ["a.py::f"], 0),
        [{"b.py::g", "b.py::i"}, {"c.py::h"}])

# 4. une feuille n'utilise rien
verifie("feuille", _uses(EDGES, ["c.py::h"], 0), [])

# 5. le regroupement par fichier reste lisible
verifie("regroupement", _group_by_file({"b.py::g", "b.py::i", "c.py::h"}),
        {"b.py": ["g", "i"], "c.py": ["h"]})

# 6. résolution du départ : symbole, fichier, nœud exact
# Un fichier part de son module ET de tout ce qu'il définit : au niveau module,
# un fichier n'a que ses imports, jamais les appels faits par ses fonctions.
graphe = {"files": {"a.py": {"defs": [{"name": "f"}]}}, "edges": EDGES}
verifie("départ par fichier", _starts_for(graphe, "a.py"),
        ["a.py::<module>", "a.py::f"])
verifie("départ par nœud exact", _starts_for(graphe, "b.py::g"), ["b.py::g"])
verifie("départ par symbole", _starts_for(graphe, "g"), ["b.py::g"])
verifie("départ inconnu", _starts_for(graphe, "inexistant"), [])

if echecs:
    print(f"ÉCHEC — {len(echecs)} test(s)")
    for e in echecs:
        print("  " + e)
    raise SystemExit(1)
print("OK — 9 tests")
