"""rank.py — affiche le top des symboles par score PageRank.

Les scores sont déjà calculés et stockés dans code_graph.json par build_graph.py
(champ `rank` de chaque définition). Ici on se contente de les classer.

Usage : python rank.py [code_graph.json] [--top 15]
"""
import json
import argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("graph", nargs="?", default="code_graph.json")
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()

    with open(args.graph, encoding="utf8") as f:
        graph = json.load(f)

    rows = []
    for rel, data in graph["files"].items():
        for d in data["defs"]:
            rows.append((d.get("rank", 0.0), f"{rel}::{d['name']}"))
    rows.sort(reverse=True)

    print(f"# Top {args.top} symboles les plus importants (PageRank)\n")
    print(f"{'score':>8}  symbole")
    print("-" * 50)
    for score, sym in rows[: args.top]:
        print(f"{score:>8.4f}  {sym}")


if __name__ == "__main__":
    main()
