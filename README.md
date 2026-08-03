# repo-map

**A navigable map of your codebase for coding agents — so they stop reading whole files just to find their bearings.**

`repo-map` is a [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server. It parses a repository into a symbol graph, ranks every symbol by importance (a tuned PageRank), and exposes a handful of tools that let an agent like Claude Code *locate* code and read *only the symbol it needs* — instead of loading entire files to orient itself.

Think of it as an "Obsidian for your codebase": an outline + a reference graph + an importance sort, queryable without opening the files.

## Why

Reading whole files to understand where a piece of logic lives is the single biggest source of wasted context in agentic coding. On a real exploration workflow over an unfamiliar Python repo, routing that navigation through `repo-map` instead of raw file reads measured:

| Metric | Result |
| --- | --- |
| Total workflow token cost | **−33 %** (up to **−52 %** cold) |
| Context loaded into the model | **−64 %** |
| `outline` vs a full file read | **−96 %** |

The gains come from never paying for a file body you don't end up editing.

## Tools

| Tool | What it does |
| --- | --- |
| `index(path)` | (Re)target the server on a repo and build its map. |
| `where_is(query)` | Find where a symbol is defined, by name (substring, case-insensitive), ranked by contextual PageRank. |
| `grep_code(pattern)` | Regex search by *content* — each hit **situated in its enclosing symbol** (`def`/`class`/`<module>`), not a bare line. |
| `outline(file)` | Table of contents of a file: class/function signatures + line ranges. ~95 % fewer tokens than reading it. |
| `get_symbol(file, name)` | The full body of a single symbol — the only thing you actually read to start coding. |
| `who_references(name)` | Who calls a symbol (what a signature change might break). |
| `what_it_uses(name, depth=1)` | The mirror: what a symbol *depends on*. Accepts a symbol, a file (everything it defines and imports) or an exact `file::symbol`. `depth=0` walks the full transitive closure — all the code actually reached from an entry point. |

## Languages

Python, JavaScript/JSX, TypeScript/TSX — via precompiled [tree-sitter](https://tree-sitter.github.io/tree-sitter/) grammars (no C toolchain required, including on Windows).

## Install

```bash
git clone https://github.com/noambinabout-boop/repo-map.git
cd repo-map
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Unix:     source .venv/bin/activate
pip install -r requirements.txt   # or: uv pip install -r requirements.txt
```

### Wire it into Claude Code

Register the server (adjust the paths to your clone):

```bash
claude mcp add repo-map -- /path/to/repo-map/.venv/bin/python /path/to/repo-map/server.py
```

Then, from any session:

```
index("/path/to/the/project/you/want/to/explore")
where_is("MyClass")
outline("src/app.py")
get_symbol("src/app.py", "MyClass")
```

The server also runs standalone over stdio (`python server.py`) for any MCP-compatible client.

## How it works

- **Symbol graph.** tree-sitter parses each file into definitions and a call/reference graph.
- **Importance ranking.** A PageRank variant weighted *against* popularity (`1/fan-in`) so ubiquitous helpers don't drown out the code that actually structures the repo, merged with the import graph so shared components/constants aren't invisible.
- **Scope resolution.** `self`/`cls`/`this`, class inheritance (Python & JS/TS `extends`), named/namespace/default imports, and light type inference (`x = Ctor(); x.foo()` → `Ctor.foo`) are resolved to the right target. Every resolution is *conservative*: when a target is ambiguous, it falls back to a broad edge rather than dropping one — it never loses an edge, at worst it adds one.
- **Incremental cache.** Parses are cached per file by mtime in `~/.repo-map/cache/` (override with `REPO_MAP_CACHE`). Nothing is written into the repos you target. First index of a 284-file TS project: ~17 s; subsequent: ~0.3 s.
- **Per-repo ignores.** Drop a `.repomapignore` (`.gitignore` syntax) at a repo root to keep generated/vendored dirs out of the graph.

## Limitations (honest)

- **PageRank is sharper on Python than on React/Expo.** Structure there flows through JSX/imports/hooks, which the call graph doesn't see. The import-graph merge fixes "invisible shared components," but entry-point screens referenced only once by a route table can still rank low.
- Name-based resolution outside the cases above may **add** a spurious edge; it never drops one.
- Python `from . import x` (no module name) is not resolved.
- repo-map indexes **structure**, not literals — use `grep_code` for flags/config strings.

## Tests

```bash
./.venv/Scripts/python.exe tests/run_tests.py
```

A non-regression suite of fixtures freezes each scope-resolution feature and compares the exact set of graph edges.

## Prior art

The "repo map" idea was pioneered by [Aider](https://aider.chat). repo-map is an independent MCP implementation with its own ranking, conservative scope resolution, and per-file incremental cache.

## License

[MIT](LICENSE)
