#!/usr/bin/env python3
"""Suite de non-regression de repo-map : les ARETES du graphe d'appels/imports.

Chaque sous-dossier de tests/fixtures/ est un mini-repo synthetique qui exerce UN
mecanisme de resolution de scope (self/this, heritage, imports nommes...). Le graphe
est construit via build_graph.build() et l'ENSEMBLE EXACT des aretes obtenues est
compare a celui declare dans le expected.json de la fixture.

  Lancer :  python tests/run_tests.py
  Figer  :  python tests/run_tests.py --record          (reecrit tous les expected.json)
  Cibler :  python tests/run_tests.py --only py_self_cls

Pourquoi comparer l'ensemble EXACT (et pas juste "contient l'arete X") : un bug de
resolution se manifeste autant par une arete EN TROP (fan-out vers un homonyme, faux
builtin resolu) que par une arete MANQUANTE. L'egalite d'ensemble attrape les deux.
Lecon recurrente du projet, gravee ici pour ne plus la reapprendre : seul le test reel
revele les trous, et il faut un harnais propre (chemins en os.path.join, pas de boucle
shell fragile) pour ne pas prendre une sortie douteuse pour une regression.
"""
import os
import sys
import json
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)  # importer build_graph depuis la racine du repo, quel que soit le cwd

from build_graph import build, SCHEMA_VERSION  # noqa: E402

FIXTURES_DIR = os.path.join(HERE, "fixtures")


def edges_of(folder):
    """Ensemble des aretes d'appel/import du graphe d'un dossier : {(caller, callee)}.
    Chaque noeud est une chaine 'relpath::symbole' (cf. build_graph.assemble)."""
    graph = build(folder)
    return {(a, b) for a, b in graph["edges"]}


def _expected_path(fixture_dir):
    return os.path.join(fixture_dir, "expected.json")


def load_expected(fixture_dir):
    with open(_expected_path(fixture_dir), encoding="utf-8") as fh:
        data = json.load(fh)
    return data, {(a, b) for a, b in data["edges"]}


def record(fixture_dir):
    """Fige expected.json depuis la sortie courante (conserve la 'description')."""
    got = edges_of(fixture_dir)
    data = {}
    if os.path.exists(_expected_path(fixture_dir)):
        with open(_expected_path(fixture_dir), encoding="utf-8") as fh:
            data = json.load(fh)
    data.setdefault("description", "")
    data["edges"] = sorted([list(e) for e in got])
    with open(_expected_path(fixture_dir), "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return len(got)


def run_one(fixture_dir):
    data, expected = load_expected(fixture_dir)
    got = edges_of(fixture_dir)
    missing = sorted(expected - got)
    extra = sorted(got - expected)
    return (not missing and not extra), missing, extra, data.get("description", "")


def _fixtures(only=None):
    names = sorted(
        d for d in os.listdir(FIXTURES_DIR)
        if os.path.isdir(os.path.join(FIXTURES_DIR, d))
    )
    return [n for n in names if not only or n == only]


def main():
    ap = argparse.ArgumentParser(description="Suite de non-regression repo-map")
    ap.add_argument("--record", action="store_true",
                    help="fige expected.json depuis la sortie courante (a n'utiliser "
                         "qu'apres avoir VERIFIE a la main que les aretes sont correctes)")
    ap.add_argument("--only", metavar="NOM", help="ne lancer qu'une fixture (nom de dossier)")
    args = ap.parse_args()

    names = _fixtures(args.only)
    print(f"repo-map tests — SCHEMA_VERSION={SCHEMA_VERSION} — {len(names)} fixture(s)\n")

    if args.record:
        for name in names:
            n = record(os.path.join(FIXTURES_DIR, name))
            print(f"  [rec]  {name}: {n} arete(s) figee(s)")
        return 0

    failed = 0
    for name in names:
        ok, missing, extra, desc = run_one(os.path.join(FIXTURES_DIR, name))
        if ok:
            print(f"  [OK]   {name} — {desc}")
        else:
            failed += 1
            print(f"  [FAIL] {name} — {desc}")
            for a, b in missing:
                print(f"           manquante : {a} -> {b}")
            for a, b in extra:
                print(f"           en trop   : {a} -> {b}")

    # Smoke test : indexer repo-map lui-meme ne doit ni crasher ni rendre un graphe vide.
    # (On ne fige pas un compte exact : il bouge a chaque evolution du code -> trop fragile.)
    if not args.only:
        try:
            n = len(edges_of(REPO))
            assert n > 0, "graphe vide"
            print(f"\n  [OK]   smoke : build(repo-map) = {n} arete(s), pas de crash")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"\n  [FAIL] smoke : build(repo-map) a leve {exc!r}")

    print(f"\n{'== TOUT PASSE ==' if not failed else '== ' + str(failed) + ' ECHEC(S) =='}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
