from __future__ import annotations

import copy
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

try:
    import ifcopenshell  # type: ignore[import-not-found]
except ImportError:
    ifcopenshell = None

DEFAULT_ROOT_ENTITY_TYPE = "IfcObjectDefinition"
DEFAULT_MAX_ENTITIES = 4000
DEFAULT_MAX_NODES = 15000
DEFAULT_MAX_EDGES = 24000
DEFAULT_IFC_ENV_VAR = "IFC_GRAPH_FILE"


@dataclass(frozen=True)
class GraphBuildOptions:
    root_entity_type: str = DEFAULT_ROOT_ENTITY_TYPE
    max_entities: int = DEFAULT_MAX_ENTITIES
    max_nodes: int = DEFAULT_MAX_NODES
    max_edges: int = DEFAULT_MAX_EDGES

    def validate(self) -> None:
        if not self.root_entity_type.strip():
            raise ValueError("root_entity_type must be a non-empty IFC class name")
        if self.max_entities <= 0 or self.max_nodes <= 0 or self.max_edges <= 0:
            raise ValueError("Limits must be positive integers")


def resolve_ifc_path(
    path: str | Path | None = None,
    *,
    default_path: str | Path | None = None,
) -> Path:
    raw_path: str | Path | None = path or os.getenv(DEFAULT_IFC_ENV_VAR) or default_path
    if raw_path is None:
        raise ValueError(
            "No IFC file was provided. Pass a path explicitly or set IFC_GRAPH_FILE."
        )

    resolved = Path(raw_path).expanduser()
    if not resolved.exists():
        raise FileNotFoundError(f"IFC file not found: {resolved}")
    return resolved.resolve()


def build_graph_from_ifc(
    path: str | Path,
    options: GraphBuildOptions | None = None,
) -> Dict[str, object]:
    _require_ifcopenshell()
    build_options = options or GraphBuildOptions()
    build_options.validate()
    resolved_path = resolve_ifc_path(path)

    model = ifcopenshell.open(str(resolved_path))

    nodes: List[dict] = []
    edges: List[dict] = []
    seen_nodes: Set[int] = set()
    seen_edges: Set[Tuple[int, int, str]] = set()

    entities = model.by_type(build_options.root_entity_type)
    for entity in entities[: build_options.max_entities]:
        _add_node(entity, nodes, seen_nodes, build_options.max_nodes)
        if len(nodes) >= build_options.max_nodes:
            break

    rels = model.by_type("IfcRelationship")
    for rel in rels:
        if len(edges) >= build_options.max_edges or len(nodes) >= build_options.max_nodes:
            break

        rtype = rel.is_a()
        rid = rel.id()

        source = getattr(rel, "RelatingObject", None) or getattr(
            rel, "RelatingStructure", None
        )
        targets = getattr(rel, "RelatedObjects", None) or getattr(
            rel, "RelatedElements", None
        )

        if source is None or not targets:
            continue

        src_id = _add_node(source, nodes, seen_nodes, build_options.max_nodes)
        if src_id is None:
            break

        for target in targets:
            if len(edges) >= build_options.max_edges or len(nodes) >= build_options.max_nodes:
                break

            dst_id = _add_node(target, nodes, seen_nodes, build_options.max_nodes)
            if dst_id is None:
                break

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
            "max_entities": build_options.max_entities,
            "max_nodes": build_options.max_nodes,
            "max_edges": build_options.max_edges,
        },
    }


def find_node(graph: Mapping[str, object], node_id: str | int) -> Dict[str, object] | None:
    target_id = str(node_id)
    for raw_node in graph.get("nodes", []):
        node = _as_mapping(raw_node)
        if str(node.get("id")) == target_id:
            return copy.deepcopy(dict(node))
    return None


def build_neighborhood(
    graph: Mapping[str, object],
    node_id: str | int,
    *,
    depth: int = 1,
) -> Dict[str, object]:
    if depth <= 0:
        raise ValueError("depth must be a positive integer")

    target_id = str(node_id)
    adjacency = build_graph_indexes(graph)["adjacency"]

    if target_id not in adjacency:
        raise KeyError(f"Node not found: {target_id}")

    visited = {target_id}
    frontier = {target_id}

    for _ in range(depth):
        next_frontier: Set[str] = set()
        for current in frontier:
            next_frontier.update(adjacency.get(current, set()))
        next_frontier -= visited
        if not next_frontier:
            break
        visited.update(next_frontier)
        frontier = next_frontier

    nodes = [
        copy.deepcopy(raw_node)
        for raw_node in graph.get("nodes", [])
        if str(_as_mapping(raw_node).get("id")) in visited
    ]
    edges = [
        copy.deepcopy(raw_edge)
        for raw_edge in graph.get("edges", [])
        if str(_as_mapping(raw_edge).get("from")) in visited
        and str(_as_mapping(raw_edge).get("to")) in visited
    ]

    return {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            **_copy_meta(graph),
            "query": {
                "type": "neighborhood",
                "node_id": target_id,
                "depth": depth,
            },
        },
    }


def build_graph_indexes(graph: Mapping[str, object]) -> Dict[str, object]:
    node_by_id: Dict[str, Dict[str, object]] = {}
    adjacency: Dict[str, Set[str]] = {}

    for raw_node in graph.get("nodes", []):
        node = dict(_as_mapping(raw_node))
        node_id = str(node["id"])
        node_by_id[node_id] = node
        adjacency.setdefault(node_id, set())

    for raw_edge in graph.get("edges", []):
        edge = _as_mapping(raw_edge)
        source = str(edge["from"])
        target = str(edge["to"])
        adjacency.setdefault(source, set()).add(target)
        adjacency.setdefault(target, set()).add(source)

    return {
        "node_by_id": node_by_id,
        "adjacency": adjacency,
    }


class IFCGraphService:
    def __init__(self, default_path: str | Path | None = None):
        self.default_path = Path(default_path).expanduser() if default_path else None
        self._cache: Dict[Tuple[str, GraphBuildOptions], Dict[str, object]] = {}

    def build_graph(
        self,
        *,
        path: str | Path | None = None,
        options: GraphBuildOptions | None = None,
        refresh: bool = False,
    ) -> Dict[str, object]:
        build_options = options or GraphBuildOptions()
        build_options.validate()
        resolved_path = resolve_ifc_path(path, default_path=self.default_path)
        cache_key = (str(resolved_path).lower(), build_options)

        if not refresh and cache_key in self._cache:
            cached = copy.deepcopy(self._cache[cache_key])
            cached["meta"] = {
                **_copy_meta(cached),
                "cached": True,
            }
            return cached

        started = time.perf_counter()
        graph = build_graph_from_ifc(resolved_path, build_options)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        graph["meta"] = {
            **_copy_meta(graph),
            "cached": False,
            "build_ms": elapsed_ms,
        }
        self._cache[cache_key] = copy.deepcopy(graph)
        return graph

    def get_node(
        self,
        node_id: str | int,
        *,
        path: str | Path | None = None,
        options: GraphBuildOptions | None = None,
        refresh: bool = False,
    ) -> Dict[str, object]:
        graph = self.build_graph(path=path, options=options, refresh=refresh)
        node = find_node(graph, node_id)
        if node is None:
            raise KeyError(f"Node not found: {node_id}")

        return {
            "node": node,
            "meta": {
                **_copy_meta(graph),
                "query": {
                    "type": "node",
                    "node_id": str(node_id),
                },
            },
        }

    def get_neighborhood(
        self,
        node_id: str | int,
        *,
        path: str | Path | None = None,
        options: GraphBuildOptions | None = None,
        depth: int = 1,
        refresh: bool = False,
    ) -> Dict[str, object]:
        graph = self.build_graph(path=path, options=options, refresh=refresh)
        return build_neighborhood(graph, node_id, depth=depth)

    def clear_cache(self) -> None:
        self._cache.clear()


def _add_node(
    entity: Any,
    nodes: List[dict],
    seen_nodes: Set[int],
    max_nodes: int,
) -> int | None:
    entity_id = entity.id()
    if entity_id in seen_nodes:
        return entity_id
    if len(nodes) >= max_nodes:
        return None

    seen_nodes.add(entity_id)
    nodes.append(
        {
            "id": entity_id,
            "label": _safe_label(entity),
            "group": entity.is_a(),
            "title": _build_title(entity),
        }
    )
    return entity_id


def _safe_label(entity: Any) -> str:
    entity_type = entity.is_a()
    global_id = getattr(entity, "GlobalId", None)
    name = getattr(entity, "Name", None)
    parts = [entity_type]
    if name:
        parts.append(str(name))
    elif global_id:
        parts.append(str(global_id))
    return " | ".join(parts)


def _build_title(entity: Any) -> str:
    return (
        f"#{entity.id()}\n"
        f"Type: {entity.is_a()}\n"
        f"Name: {getattr(entity, 'Name', '')}"
    )


def _require_ifcopenshell() -> None:
    if ifcopenshell is None:
        raise RuntimeError(
            "ifcopenshell is not installed. Run: pip install ifcopenshell"
        )


def _copy_meta(graph: Mapping[str, object]) -> Dict[str, object]:
    return dict(_as_mapping(graph.get("meta", {})))


def _as_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError("Expected a mapping")
    return value


__all__ = [
    "DEFAULT_IFC_ENV_VAR",
    "DEFAULT_MAX_EDGES",
    "DEFAULT_MAX_ENTITIES",
    "DEFAULT_MAX_NODES",
    "DEFAULT_ROOT_ENTITY_TYPE",
    "GraphBuildOptions",
    "IFCGraphService",
    "build_graph_from_ifc",
    "build_graph_indexes",
    "build_neighborhood",
    "find_node",
    "resolve_ifc_path",
]
