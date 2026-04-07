# Using This In Another System

The refactor keeps the graph output the same as the original app and only makes the code more reusable internally.

That means:

- the browser viewer still receives the same graph structure
- `/graph-data` still returns the same kind of JSON
- another Python project can now import the IFC graph code directly from [`ifc_graph.py`](../ifc_graph.py)

## What stayed the same

The graph format is still:

```json
{
  "nodes": [
    {
      "id": 123,
      "label": "IfcWall | Exterior Wall 01",
      "group": "IfcWall",
      "title": "#123\nType: IfcWall\nName: Exterior Wall 01"
    }
  ],
  "edges": [
    {
      "id": "244-12-123",
      "from": 12,
      "to": 123,
      "label": "IfcRelContainedInSpatialStructure"
    }
  ],
  "meta": {
    "max_entities": 800,
    "max_nodes": 5000,
    "max_edges": 8000
  }
}
```

The FastAPI app still adds:

- `cached`
- `build_ms`

inside `meta`, just like before.

## What changed internally

The IFC parsing and graph-building logic now lives in [`ifc_graph.py`](../ifc_graph.py) instead of being embedded directly in `main.py`.

That file exposes:

- `GraphBuildOptions`
- `build_graph_from_ifc(...)`
- `IFCGraphService`
- `find_node(...)`
- `build_neighborhood(...)`
- `build_graph_indexes(...)`

So another Python service can reuse the same graph builder without copying the FastAPI app.

## Simplest import example

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

## Direct function example

```python
from pathlib import Path

from ifc_graph import GraphBuildOptions, build_graph_from_ifc

graph = build_graph_from_ifc(
    Path("project.ifc"),
    GraphBuildOptions(
        max_entities=500,
        max_nodes=3000,
        max_edges=5000,
    ),
)
```

Use this when you want:

- a script
- a notebook
- an ETL job
- an offline export step

## Reusing the service layer

`IFCGraphService` adds in-memory caching and helper methods for programmatic use.

Example:

```python
from ifc_graph import GraphBuildOptions, IFCGraphService

service = IFCGraphService(default_path="project.ifc")
options = GraphBuildOptions(max_entities=600, max_nodes=2200, max_edges=4000)

graph = service.build_graph(options=options)
node = service.get_node(graph["nodes"][0]["id"], options=options)
subgraph = service.get_neighborhood(graph["nodes"][0]["id"], depth=1, options=options)
```

These helpers are for Python reuse only. They do not change the public `/graph-data` response format.

## Using another IFC file

If you are importing the module directly, pass a different path:

```python
service = IFCGraphService(default_path="C:/models/hospital.ifc")
```

Or:

```python
graph = build_graph_from_ifc("C:/models/hospital.ifc")
```

If you are running the FastAPI app, set:

```powershell
$env:IFC_GRAPH_FILE="C:\models\hospital.ifc"
uvicorn main:app --reload
```

## Practical takeaway

If you want compatibility, use `/graph-data` exactly as before.

If you want reuse, import [`ifc_graph.py`](../ifc_graph.py) from another Python codebase and keep the same graph structure everywhere.
