# IFC Knowledge Graph

This app reads `project.ifc` from the repo root and creates the same browser-based knowledge graph as before, but the IFC-to-graph code now lives in a reusable module: [`ifc_graph.py`](./ifc_graph.py).

The important compatibility point is that the graph shape returned by the app is unchanged:

- nodes still look like `{ id, label, group, title }`
- edges still look like `{ id, from, to, label }`
- `GET /graph-data` still returns `{ nodes, edges, meta }`

## Install

```powershell
pip install -r requirements.txt
```

## Run server

```powershell
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000`

You can also override the default IFC file without changing code:

```powershell
$env:IFC_GRAPH_FILE="C:\path\to\another.ifc"
uvicorn main:app --reload
```

<img src="readme\graphimage.png" alt="visual" style="width:100%;">

## API

- `GET /`
  HTML graph viewer
- `GET /graph-data`
  JSON with graph nodes and edges

Query string support is also unchanged:

`/graph-data?max_entities=600&max_nodes=2200&max_edges=4000`

Use `refresh=true` to rebuild and bypass cache:

`/graph-data?max_entities=600&max_nodes=2200&max_edges=4000&refresh=true`

## Reuse in another system

The reuse work is internal and import-based rather than changing the public graph shape.

Example:

```python
from pathlib import Path

from ifc_graph import GraphBuildOptions, IFCGraphService

service = IFCGraphService(default_path=Path("project.ifc"))
graph = service.build_graph(
    options=GraphBuildOptions(
        max_entities=800,
        max_nodes=4000,
        max_edges=6000,
    )
)

print(graph["nodes"][0])
print(graph["edges"][0])
```

See [`docs/USE_IN_OTHER_SYSTEMS.md`](./docs/USE_IN_OTHER_SYSTEMS.md) for the integration guide.
