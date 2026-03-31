# IFC Knowledge Graph (FastAPI + HTML)

This app reads a file called 'project.ifc' placed in the root directory and creates a browser-based knowledge graph.

## 1) Install dependencies

```powershell
pip install -r requirements.txt
```

## 2) Run server

```powershell
uvicorn main:app --reload
```

## 3) Open

Visit: `http://127.0.0.1:8000`

<img src="readme\graphimage.png" alt="visual" style="width:100%;">

## Large IFC Performance Notes

For a larger IFC for example, first parse can still take some time:

- First load builds graph JSON and reports build time in the page header
- Subsequent loads with the same limits are served from cache

You can tune limits from the API query string:

`/graph-data?max_entities=600&max_nodes=2200&max_edges=4000`

Use `refresh=true` to rebuild and bypass cache:

`/graph-data?max_entities=600&max_nodes=2200&max_edges=4000&refresh=true`

## API

- `GET /` -> HTML graph viewer
- `GET /graph-data` -> JSON with graph nodes and edges
