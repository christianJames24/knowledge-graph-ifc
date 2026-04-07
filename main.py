from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ifc_graph import (
    DEFAULT_MAX_EDGES,
    DEFAULT_MAX_ENTITIES,
    DEFAULT_MAX_NODES,
    GraphBuildOptions,
    IFCGraphService,
)

app = FastAPI(title="IFC Knowledge Graph")

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))
IFC_FILE = BASE_DIR / "project.ifc"

graph_service = IFCGraphService(default_path=IFC_FILE)


def _build_options(
    *,
    max_entities: int,
    max_nodes: int,
    max_edges: int,
) -> GraphBuildOptions:
    options = GraphBuildOptions(
        max_entities=max_entities,
        max_nodes=max_nodes,
        max_edges=max_edges,
    )
    options.validate()
    return options


def _as_http_exception(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, KeyError):
        detail = exc.args[0] if exc.args else str(exc)
        return HTTPException(status_code=404, detail=str(detail))
    return HTTPException(status_code=500, detail=str(exc))


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return TEMPLATES.TemplateResponse("index.html", {"request": request})


@app.get("/graph-data")
def graph_data(
    max_entities: int = DEFAULT_MAX_ENTITIES,
    max_nodes: int = DEFAULT_MAX_NODES,
    max_edges: int = DEFAULT_MAX_EDGES,
    refresh: bool = False,
):
    try:
        options = _build_options(
            max_entities=max_entities,
            max_nodes=max_nodes,
            max_edges=max_edges,
        )
        return graph_service.build_graph(
            options=options,
            refresh=refresh,
        )
    except Exception as exc:
        raise _as_http_exception(exc) from exc
