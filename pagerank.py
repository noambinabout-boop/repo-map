"""pagerank.py — PageRank sur un graphe d'arêtes (appelant -> appelé).

Un symbole est important s'il est appelé par des symboles eux-mêmes importants.
Même algo que Google, appliqué aux appels de fonctions.
"""
from collections import defaultdict


def pagerank(edges, damping=0.85, iters=40):
    """edges : itérable de (src, dst) ou (src, dst, poids). Le poids ∈ (0,1] est un facteur
    d'ABSORPTION de la CIBLE : un nœud répartit son rank également entre ses appels (comme
    le PageRank classique), mais chaque cible n'en ABSORBE que `poids` (le reste se dissipe).
    Sans poids -> 1.0 = ancien comportement exact. Sert à pénaliser globalement les symboles
    ubiquitaires (poids faible) sans que la normalisation par source n'annule l'effet."""
    nodes = set()
    out_links = defaultdict(list)   # src -> [(dst, poids), ...]
    for e in edges:
        src, dst = e[0], e[1]
        w = e[2] if len(e) > 2 else 1.0
        nodes.add(src)
        nodes.add(dst)
        out_links[src].append((dst, w))

    n = len(nodes)
    if n == 0:
        return {}
    rank = {node: 1.0 / n for node in nodes}

    for _ in range(iters):
        new_rank = {node: (1.0 - damping) / n for node in nodes}
        dangling = 0.0
        for node in nodes:
            links = out_links.get(node)
            if links:
                base = damping * rank[node] / len(links)   # split égal (PageRank classique)
                for dst, w in links:
                    new_rank[dst] += base * w               # la cible n'absorbe que `w`
            else:
                dangling += damping * rank[node] / n
        if dangling:
            for node in nodes:
                new_rank[node] += dangling
        rank = new_rank
    return rank
