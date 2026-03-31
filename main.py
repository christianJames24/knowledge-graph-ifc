from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, List, Set, Tuple

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request

try:
    import ifcopenshell  # type: ignore[import-not-found]
except ImportError:
    ifcopenshell = None

app = FastAPI(title="IFC Knowledge Graph")

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))
IFC_FILE = BASE_DIR / "project.ifc"

DEFAULT_MAX_CORE_ENTITIES = 4000
DEFAULT_MAX_NODES = 15000
DEFAULT_MAX_EDGES = 24000

_GRAPH_CACHE: Dict[Tuple[int, int, int], Dict[str, object]] = {}


def _safe_label(entity) -> str:
    etype = entity.is_a()
    gid = getattr(entity, "GlobalId", None)
    name = getattr(entity, "Name", None)
    parts = [etype]
    if name:
        parts.append(str(name))
    elif gid:
        parts.append(str(gid))
    return " | ".join(parts)


def build_graph_from_ifc(
    path: Path,
    max_entities: int = DEFAULT_MAX_CORE_ENTITIES,
    max_nodes: int = DEFAULT_MAX_NODES,
    max_edges: int = DEFAULT_MAX_EDGES,
) -> Dict[str, object]:
    if ifcopenshell is None:
        raise RuntimeError(
            "ifcopenshell is not installed. Run: pip install ifcopenshell"
        )
    if not path.exists():
        raise FileNotFoundError(f"IFC file not found: {path}")

    model = ifcopenshell.open(str(path))

    nodes: List[dict] = []
    edges: List[dict] = []
    seen_nodes: Set[int] = set()
    seen_edges: Set[Tuple[int, int, str]] = set()

    entities = model.by_type("IfcObjectDefinition")

    for entity in entities[:max_entities]:
        eid = entity.id()
        if eid in seen_nodes:
            continue
        if len(nodes) >= max_nodes:
            break
        seen_nodes.add(eid)
        nodes.append(
            {
                "id": eid,
                "label": _safe_label(entity),
                "group": entity.is_a(),
                "title": f"#{eid}\\nType: {entity.is_a()}\\nName: {getattr(entity, 'Name', '')}",
            }
        )

    rels = model.by_type("IfcRelationship")
    for rel in rels:
        if len(edges) >= max_edges or len(nodes) >= max_nodes:
            break

        rtype = rel.is_a()
        rid = rel.id()

        source = getattr(rel, "RelatingObject", None) or getattr(rel, "RelatingStructure", None)
        targets = getattr(rel, "RelatedObjects", None) or getattr(rel, "RelatedElements", None)

        if source is not None and targets:
            src_id = source.id()
            if src_id not in seen_nodes:
                if len(nodes) >= max_nodes:
                    break
                seen_nodes.add(src_id)
                nodes.append(
                    {
                        "id": src_id,
                        "label": _safe_label(source),
                        "group": source.is_a(),
                        "title": f"#{src_id}\\nType: {source.is_a()}\\nName: {getattr(source, 'Name', '')}",
                    }
                )

            for target in targets:
                if len(edges) >= max_edges or len(nodes) >= max_nodes:
                    break

                dst_id = target.id()
                if dst_id not in seen_nodes:
                    if len(nodes) >= max_nodes:
                        break
                    seen_nodes.add(dst_id)
                    nodes.append(
                        {
                            "id": dst_id,
                            "label": _safe_label(target),
                            "group": target.is_a(),
                            "title": f"#{dst_id}\\nType: {target.is_a()}\\nName: {getattr(target, 'Name', '')}",
                        }
                    )

                key = (src_id, dst_id, rtype)
                if key in seen_edges:
                    continue
                seen_edges.add(key)
                edges.append(
                    {
                        "id": f"{rid}-{src_id}-{dst_id}",
                        "from": src_id,
                        "to": dst_id,
                        "label": rtype,
                    }
                )

    return {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "max_entities": max_entities,
            "max_nodes": max_nodes,
            "max_edges": max_edges,
        },
    }


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return TEMPLATES.TemplateResponse("index.html", {"request": request})


@app.get("/graph-data")
def graph_data(
    max_entities: int = DEFAULT_MAX_CORE_ENTITIES,
    max_nodes: int = DEFAULT_MAX_NODES,
    max_edges: int = DEFAULT_MAX_EDGES,
    refresh: bool = False,
):
    try:
        if max_entities <= 0 or max_nodes <= 0 or max_edges <= 0:
            raise HTTPException(status_code=400, detail="Limits must be positive integers")

        cache_key = (max_entities, max_nodes, max_edges)
        if not refresh and cache_key in _GRAPH_CACHE:
            cached = _GRAPH_CACHE[cache_key]
            return {
                **cached,
                "meta": {
                    **cached.get("meta", {}),
                    "cached": True,
                },
            }

        started = time.perf_counter()
        graph = build_graph_from_ifc(
            IFC_FILE,
            max_entities=max_entities,
            max_nodes=max_nodes,
            max_edges=max_edges,
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        graph_meta = {
            **graph.get("meta", {}),
            "cached": False,
            "build_ms": elapsed_ms,
        }
        graph["meta"] = graph_meta
        _GRAPH_CACHE[cache_key] = graph
        return graph
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
