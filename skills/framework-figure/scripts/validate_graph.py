#!/usr/bin/env python3
"""Validate a framework-figure module-flow specification."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


Edge = tuple[str, str, str]


def _is_record(value: Any) -> bool:
    return isinstance(value, dict)


def _read_edge(value: Any, location: str, errors: list[str]) -> Edge | None:
    if not _is_record(value):
        errors.append(f"{location} must be an object")
        return None
    source = value.get("from")
    target = value.get("to")
    edge_type = value.get("type", "flow")
    valid = True
    if not isinstance(source, str) or not source:
        errors.append(f"{location}.from must be a non-empty string")
        valid = False
    if not isinstance(target, str) or not target:
        errors.append(f"{location}.to must be a non-empty string")
        valid = False
    if not isinstance(edge_type, str) or not edge_type:
        errors.append(f"{location}.type must be a non-empty string")
        valid = False
    return (source, target, edge_type) if valid else None


def _read_edge_list(
    constraints: dict[str, Any], key: str, errors: list[str]
) -> list[Edge]:
    value = constraints.get(key, [])
    if not isinstance(value, list):
        errors.append(f"constraints.{key} must be a list")
        return []
    result: list[Edge] = []
    for index, item in enumerate(value):
        edge = _read_edge(item, f"constraints.{key}[{index}]", errors)
        if edge is not None:
            result.append(edge)
    return result


def _read_adjacency_constraint(
    constraints: dict[str, Any], key: str, errors: list[str]
) -> dict[str, set[str]]:
    value = constraints.get(key, {})
    if not isinstance(value, dict):
        errors.append(f"constraints.{key} must be an object mapping node IDs to lists")
        return {}
    result: dict[str, set[str]] = {}
    for node_id, adjacent in value.items():
        if not isinstance(node_id, str) or not node_id:
            errors.append(f"constraints.{key} contains an invalid node ID")
            continue
        if not isinstance(adjacent, list) or not all(
            isinstance(item, str) and item for item in adjacent
        ):
            errors.append(f"constraints.{key}.{node_id} must be a list of node IDs")
            continue
        if len(set(adjacent)) != len(adjacent):
            errors.append(f"constraints.{key}.{node_id} contains duplicate node IDs")
        result[node_id] = set(adjacent)
    return result


def _find_cycle(nodes: set[str], flow_edges: set[Edge]) -> list[str] | None:
    adjacency: dict[str, list[str]] = defaultdict(list)
    for source, target, _ in flow_edges:
        adjacency[source].append(target)

    state: dict[str, int] = {node_id: 0 for node_id in nodes}
    stack: list[str] = []

    def visit(node_id: str) -> list[str] | None:
        state[node_id] = 1
        stack.append(node_id)
        for target in adjacency[node_id]:
            if state[target] == 0:
                cycle = visit(target)
                if cycle:
                    return cycle
            elif state[target] == 1:
                start = stack.index(target)
                return stack[start:] + [target]
        stack.pop()
        state[node_id] = 2
        return None

    for node_id in sorted(nodes):
        if state[node_id] == 0:
            cycle = visit(node_id)
            if cycle:
                return cycle
    return None


def validate(spec: Any) -> list[str]:
    errors: list[str] = []
    if not _is_record(spec):
        return ["top-level JSON value must be an object"]

    raw_nodes = spec.get("nodes")
    if not isinstance(raw_nodes, list):
        return ["nodes must be a list"]

    node_ids: list[str] = []
    for index, node in enumerate(raw_nodes):
        if not _is_record(node):
            errors.append(f"nodes[{index}] must be an object")
            continue
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id:
            errors.append(f"nodes[{index}].id must be a non-empty string")
            continue
        node_ids.append(node_id)
        label = node.get("label")
        if label is not None and not isinstance(label, str):
            errors.append(f"nodes[{index}].label must be a string when provided")

    duplicates = sorted({node_id for node_id in node_ids if node_ids.count(node_id) > 1})
    for node_id in duplicates:
        errors.append(f"duplicate node ID: {node_id}")
    nodes = set(node_ids)

    raw_edges = spec.get("edges")
    if not isinstance(raw_edges, list):
        errors.append("edges must be a list")
        raw_edges = []

    edges: list[Edge] = []
    for index, item in enumerate(raw_edges):
        edge = _read_edge(item, f"edges[{index}]", errors)
        if edge is None:
            continue
        source, target, _ = edge
        if source not in nodes:
            errors.append(f"edges[{index}] references unknown source node: {source}")
        if target not in nodes:
            errors.append(f"edges[{index}] references unknown target node: {target}")
        edges.append(edge)

    if len(set(edges)) != len(edges):
        errors.append("duplicate edge found")

    raw_constraints = spec.get("constraints", {})
    if not isinstance(raw_constraints, dict):
        errors.append("constraints must be an object")
        raw_constraints = {}

    required = _read_edge_list(raw_constraints, "required_edges", errors)
    forbidden = _read_edge_list(raw_constraints, "forbidden_edges", errors)
    edge_set = set(edges)
    for edge in required:
        if edge not in edge_set:
            errors.append(f"required edge missing: {edge[0]} -> {edge[1]} ({edge[2]})")
    for edge in forbidden:
        if edge in edge_set:
            errors.append(f"forbidden edge present: {edge[0]} -> {edge[1]} ({edge[2]})")

    flow_edges = {edge for edge in edges if edge[2] == "flow"}
    incoming: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    outgoing: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    for source, target, _ in flow_edges:
        if source in nodes and target in nodes:
            outgoing[source].add(target)
            incoming[target].add(source)

    expected_in = _read_adjacency_constraint(raw_constraints, "exact_incoming", errors)
    expected_out = _read_adjacency_constraint(raw_constraints, "exact_outgoing", errors)
    for node_id, expected in expected_in.items():
        if node_id not in nodes:
            errors.append(f"constraints.exact_incoming references unknown node: {node_id}")
            continue
        unknown = expected - nodes
        if unknown:
            errors.append(
                f"constraints.exact_incoming.{node_id} references unknown nodes: "
                + ", ".join(sorted(unknown))
            )
        actual = incoming[node_id]
        if actual != expected:
            errors.append(
                f"exact incoming mismatch for {node_id}: expected "
                f"{sorted(expected)}, found {sorted(actual)}"
            )
    for node_id, expected in expected_out.items():
        if node_id not in nodes:
            errors.append(f"constraints.exact_outgoing references unknown node: {node_id}")
            continue
        unknown = expected - nodes
        if unknown:
            errors.append(
                f"constraints.exact_outgoing.{node_id} references unknown nodes: "
                + ", ".join(sorted(unknown))
            )
        actual = outgoing[node_id]
        if actual != expected:
            errors.append(
                f"exact outgoing mismatch for {node_id}: expected "
                f"{sorted(expected)}, found {sorted(actual)}"
            )

    acyclic_flow = raw_constraints.get("acyclic_flow", False)
    if not isinstance(acyclic_flow, bool):
        errors.append("constraints.acyclic_flow must be true or false")
    elif acyclic_flow:
        valid_flow_edges = {
            edge for edge in flow_edges if edge[0] in nodes and edge[1] in nodes
        }
        cycle = _find_cycle(nodes, valid_flow_edges)
        if cycle:
            errors.append("flow cycle found: " + " -> ".join(cycle))

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check graph-spec.json workflow connections and declared constraints."
    )
    parser.add_argument("spec", type=Path, help="path to the graph specification JSON")
    args = parser.parse_args()

    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"ERROR: cannot read {args.spec}: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}", file=sys.stderr)
        return 2

    errors = validate(spec)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    edge_count = len(spec.get("edges", []))
    print(f"OK: {len(spec['nodes'])} nodes and {edge_count} edges satisfy the declared constraints.")
    print("Reminder: structural validity does not establish scientific correctness.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
