"""viz_serve.py — la viz standalone de repo-map (« Obsidian de codebase »).

Sert une page web (force-graph) + le graphe AGRÉGÉ AU NIVEAU FICHIER : un nœud par
fichier (taille = importance PageRank cumulée, couleur = module), arêtes = appels
inter-fichiers (épaisseur = nombre d'appels). V1a : vue fichiers seulement (le dépliage
en symboles + le panneau outline = V1b).

Usage : python viz_serve.py <dossier> [--port 8765] [--no-open]
Une commande, ça tourne : build le graphe, sert la page, ouvre le navigateur.
"""
import os
import sys
import json
import argparse
import webbrowser
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, HTTPServer

from build_graph import build, rerank, apply_ranks

HERE = os.path.dirname(os.path.abspath(__file__))
VIZ_DIR = os.path.join(HERE, "viz")

PAYLOAD = {"nodes": [], "links": [], "target": ""}


def file_payload(graph, target):
    """code_graph.json -> {nodes, links} agrégés au niveau FICHIER."""
    files = graph["files"]
    nodes = []
    for rel, data in files.items():
        rank = sum(d.get("rank", 0.0) for d in data["defs"])
        module = rel.split("/")[0] if "/" in rel else rel  # dossier top-level, sinon le fichier
        syms = [{
            "name": d["name"], "kind": d["kind"], "signature": d["signature"],
            "line": d["line"], "end_line": d["end_line"], "rank": d.get("rank", 0.0),
        } for d in data["defs"]]
        syms.sort(key=lambda s: s["rank"], reverse=True)   # plus important en premier
        nodes.append({
            "id": rel,
            "label": rel.split("/")[-1],
            "module": module,
            "rank": round(rank, 6),
            "ndefs": len(data["defs"]),
            "symbols": syms,
        })
    # arêtes fichier -> fichier (on exclut les appels internes au même fichier),
    # pondérées par le nombre d'appels.
    pair = defaultdict(int)
    for src, dst in graph["edges"]:
        sf = src.split("::")[0]
        df = dst.split("::")[0]
        if sf != df and sf in files and df in files:
            pair[(sf, df)] += 1
    links = [{"source": s, "target": t, "count": c} for (s, t), c in pair.items()]
    return {"nodes": nodes, "links": links, "target": target}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._file(os.path.join(VIZ_DIR, "index.html"), "text/html")
        elif self.path == "/graph.json":
            self._send(200, "application/json",
                       json.dumps(PAYLOAD, ensure_ascii=False).encode("utf8"))
        else:
            self._send(404, "text/plain", b"not found")

    def _file(self, path, ctype):
        try:
            with open(path, "rb") as f:
                self._send(200, ctype, f.read())
        except OSError:
            self._send(404, "text/plain", b"not found")

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass  # serveur silencieux


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()

    target = os.path.abspath(args.folder)
    graph = build(target)
    # la viz est un instantané statique -> rank SANS contexte de session (neutre), comme
    # avant que server.py devienne session-aware (cf. build_graph.rerank).
    ranks = rerank(graph["files"], graph["edges"], graph["import_edges"])
    apply_ranks(graph["files"], graph["symbols"], ranks)
    global PAYLOAD
    PAYLOAD = file_payload(graph, target)
    n_links = len(PAYLOAD["links"])
    print(f"Graphe : {len(PAYLOAD['nodes'])} fichiers, {n_links} liens inter-fichiers.")

    url = f"http://localhost:{args.port}"
    print(f"Viz repo-map en ligne : {url}   (cible : {target})")
    print("Ctrl+C pour arrêter.")
    if not args.no_open:
        webbrowser.open(url)
    HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nArrêt.")
        sys.exit(0)
