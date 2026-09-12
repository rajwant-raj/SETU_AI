"""SETU Route Candidate Generation v0.1 (Checkpoint 13).

Generates physically plausible alternative route candidates from normalized road network
segments using an in-memory graph representation and Yen's K-shortest simple paths algorithm.

Separation of Concerns:
- Candidate Generation (Checkpoint 13) answers: "What physically plausible routes exist?"
- Route Ranking (Checkpoint 14) answers: "Which candidate is best under ETA/risk/accessibility?"
Therefore, this module contains ZERO ranking formulas, risk scores, accessibility scores,
weather weighting, vehicle suitability, or ETA calculations.

Graph Model & Operational Limitations:
- Endpoints of normalized road segments represent graph nodes.
- Each normalized segment forms an edge.
- Bidirectional network assumption: The current normalized OSM road-segment representation
  does not yet retain or validate 'oneway' directional tagging. Therefore, segments are
  treated as bidirectional in the in-memory routing graph. This is an explicit physical-layer
  approximation for candidate generation and not production-grade directional turn-by-turn
  navigation.
- Pure Python standard library only: Zero external routing APIs (no Mapbox, OSRM, Google),
  zero ML, zero external services, and zero message brokers.
"""

from __future__ import annotations

import heapq
import itertools
import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Tuple

from src.impact.network_impact import haversine_km

# Coordinate quantization precision (6 decimal places is ~0.11m resolution)
COORD_ROUND_DECIMALS = 6


class RouteCandidateValidationError(ValueError):
    """Raised when network segments, coordinates, or generation parameters are invalid."""
    pass


def _coord_to_node_id(lat: float, lon: float) -> str:
    """Deterministically convert WGS84 coordinate to a stable node ID.

    Normalizes negative zero floats to positive zero to guarantee stable keys.
    """
    r_lat = round(lat, COORD_ROUND_DECIMALS)
    r_lon = round(lon, COORD_ROUND_DECIMALS)
    if abs(r_lat) == 0.0:
        r_lat = 0.0
    if abs(r_lon) == 0.0:
        r_lon = 0.0
    return f"N_{r_lat:.6f}_{r_lon:.6f}"


def _validate_numeric(field: str, val: Any, min_val: float | None = None, max_val: float | None = None) -> float:
    """Validate that a value is a finite number within optional bounds."""
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise RouteCandidateValidationError(f"Field '{field}' must be numeric, got {type(val).__name__} ({val!r})")
    f_val = float(val)
    if not math.isfinite(f_val):
        raise RouteCandidateValidationError(f"Field '{field}' must be finite, got {f_val}")
    if min_val is not None and f_val < min_val:
        raise RouteCandidateValidationError(f"Field '{field}' must be >= {min_val}, got {f_val}")
    if max_val is not None and f_val > max_val:
        raise RouteCandidateValidationError(f"Field '{field}' must be <= {max_val}, got {f_val}")
    return f_val


def _validate_coord(field: str, val: Any, min_val: float, max_val: float) -> float:
    """Validate coordinate within bounds."""
    return _validate_numeric(field, val, min_val, max_val)


def _validate_endpoint(name: str, endpoint: Mapping[str, Any]) -> Tuple[float, float]:
    """Validate an origin or destination coordinate mapping."""
    if not isinstance(endpoint, Mapping):
        raise RouteCandidateValidationError(f"Expected {name} to be a mapping, got {type(endpoint).__name__}")
    if "latitude" not in endpoint or endpoint["latitude"] is None:
        raise RouteCandidateValidationError(f"{name} must contain 'latitude'")
    if "longitude" not in endpoint or endpoint["longitude"] is None:
        raise RouteCandidateValidationError(f"{name} must contain 'longitude'")

    lat = _validate_coord(f"{name}.latitude", endpoint["latitude"], -90.0, 90.0)
    lon = _validate_coord(f"{name}.longitude", endpoint["longitude"], -180.0, 180.0)
    return lat, lon


def _resolve_nearest_node(
    target_lat: float,
    target_lon: float,
    node_coords: Mapping[str, Tuple[float, float]],
) -> str:
    """Resolve a target coordinate to the nearest existing node in the graph via haversine distance."""
    if not node_coords:
        raise RouteCandidateValidationError("Cannot resolve coordinates on an empty network")

    best_node: Optional[str] = None
    best_dist = float("inf")

    # Sorted iteration for deterministic tie-breaking
    for node_id in sorted(node_coords.keys()):
        n_lat, n_lon = node_coords[node_id]
        d = haversine_km(target_lat, target_lon, n_lat, n_lon)
        if d < best_dist:
            best_dist = d
            best_node = node_id

    if best_node is None:
        raise RouteCandidateValidationError("Failed to resolve nearest node")
    return best_node


def _dijkstra_shortest_path(
    adj: Mapping[str, List[Dict[str, Any]]],
    source: str,
    target: str,
    banned_edges: Set[Tuple[str, str, str]],
    banned_nodes: Set[str],
) -> Optional[Dict[str, Any]]:
    """Deterministic Dijkstra shortest simple path between source and target.

    Args:
        adj: Adjacency list mapping node_id -> list of edge dicts:
             {"neighbor": v, "weight": float, "segment_id": str, "segment": dict}
        source: Starting node ID.
        target: Destination node ID.
        banned_edges: Set of (u, v, segment_id) tuples that cannot be traversed.
        banned_nodes: Set of node IDs that cannot be visited (except source and target).

    Returns:
        Path dictionary {"nodes": list, "segments": list, "total_distance_km": float} or None.
    """
    if source in banned_nodes or target in banned_nodes:
        return None

    counter = itertools.count()

    # Priority queue item:
    # (cost, hop_count, seg_ids_tuple, path_nodes_tuple, entry_id, current_node, path_nodes, path_edges)
    # Monotonic entry_id guarantees Python never attempts comparing dicts inside path_edges.
    pq: List[Tuple[float, int, Tuple[str, ...], Tuple[str, ...], int, str, List[str], List[Dict[str, Any]]]] = []
    heapq.heappush(pq, (0.0, 0, (), (source,), next(counter), source, [source], []))

    visited: Set[str] = set()

    while pq:
        cost, _, _, _, _, u, path_nodes, path_edges = heapq.heappop(pq)

        if u in visited:
            continue
        visited.add(u)

        if u == target:
            rounded_dist = round(sum(s["segment_length_km"] for s in path_edges), 6)
            return {
                "nodes": path_nodes,
                "segments": path_edges,
                "total_distance_km": rounded_dist,
            }

        neighbors = adj.get(u, [])
        for edge in neighbors:
            v = edge["neighbor"]
            seg_id = edge["segment_id"]
            weight = edge["weight"]

            # Edge or node banned
            if v in banned_nodes:
                continue
            if (u, v, seg_id) in banned_edges:
                continue
            # Already settled or cycle in path
            if v in visited:
                continue
            if v in path_nodes:
                continue

            new_cost = cost + weight
            new_path_nodes = list(path_nodes)
            new_path_nodes.append(v)
            new_path_edges = list(path_edges)
            new_path_edges.append(edge["segment"])
            new_seg_ids = tuple(s["segment_id"] for s in new_path_edges)

            heapq.heappush(
                pq,
                (
                    new_cost,
                    len(new_path_edges),
                    new_seg_ids,
                    tuple(new_path_nodes),
                    next(counter),
                    v,
                    new_path_nodes,
                    new_path_edges,
                ),
            )

    return None


def generate_route_candidates(
    network_segments: Iterable[Mapping[str, Any]],
    origin: Mapping[str, Any],
    destination: Mapping[str, Any],
    k: int = 3,
    blocked_segment_ids: Optional[Iterable[Any]] = None,
) -> List[Dict[str, Any]]:
    """Generate up to k distinct simple route candidates between origin and destination.

    Uses an in-memory graph formed from normalized segment endpoints and Yen's
    K-shortest simple paths algorithm based strictly on physical road distance.

    Candidate Generation answers: "What physically plausible routes exist?"
    Route Ranking (Checkpoint 14) answers: "Which candidate is best under ETA/risk/accessibility?"
    This function computes ZERO risk scores, accessibility scores, ETAs, or recommendation scores.

    Args:
        network_segments: Iterable of segment mappings. Each must contain:
            segment_id, start_latitude, start_longitude, end_latitude, end_longitude, segment_length_km.
            Preserves extra segment metadata without mutating caller input.
        origin: Mapping with 'latitude' and 'longitude'.
        destination: Mapping with 'latitude' and 'longitude'.
        k: Positive integer number of alternative routes to generate (default 3).
        blocked_segment_ids: Optional set/list of segment IDs to exclude from routing.
            Note: "potentially affected" segments from Network Impact do not automatically
            mean blocked; only explicitly supplied blocked IDs are excluded.

    Returns:
        List of candidate route dictionaries sorted from shortest to longest physical distance.
        Each candidate contains:
            - route_id: str (e.g. 'candidate_001')
            - segment_ids: List[str]
            - node_ids: List[str]
            - origin_node: str
            - destination_node: str
            - total_distance_km: float
            - segment_count: int
            - geometry: List[List[float]] ([lat, lon] sequence)
            - segments: List[Dict[str, Any]] (ordered segment records with preserved metadata)

    Raises:
        RouteCandidateValidationError: If input networks, coordinates, k, or blocked IDs are
            malformed/invalid, or if origin and destination are disconnected in the network.
    """
    if network_segments is None:
        raise RouteCandidateValidationError("Expected network_segments to be an iterable, got None")
    if isinstance(network_segments, (str, bytes, Mapping)):
        raise RouteCandidateValidationError(
            f"Expected network_segments to be an iterable of segments, got {type(network_segments).__name__}"
        )

    try:
        segments_iter = iter(network_segments)
    except TypeError as exc:
        raise RouteCandidateValidationError(
            f"Expected network_segments to be an iterable, got {type(network_segments).__name__}"
        ) from exc

    if isinstance(k, bool) or not isinstance(k, int) or k <= 0:
        raise RouteCandidateValidationError(f"Parameter 'k' must be a positive integer, got {k!r}")

    orig_lat, orig_lon = _validate_endpoint("origin", origin)
    dest_lat, dest_lon = _validate_endpoint("destination", destination)

    blocked_set: Set[str] = set()
    if blocked_segment_ids is not None:
        if isinstance(blocked_segment_ids, (str, bytes)):
            raise RouteCandidateValidationError("blocked_segment_ids must be an iterable of IDs, not a string")
        try:
            blocked_set = {str(bid).strip() for bid in blocked_segment_ids if str(bid).strip()}
        except TypeError as exc:
            raise RouteCandidateValidationError(f"Invalid blocked_segment_ids: {exc}") from exc

    # 1. In-memory Graph Construction
    node_coords: Dict[str, Tuple[float, float]] = {}
    adj: Dict[str, List[Dict[str, Any]]] = {}

    segment_count_seen = 0

    for raw_seg in segments_iter:
        if not isinstance(raw_seg, Mapping):
            raise RouteCandidateValidationError(f"Expected segment mapping, got {type(raw_seg).__name__}")
        segment_count_seen += 1

        seg_id = raw_seg.get("segment_id")
        if seg_id is None or not str(seg_id).strip():
            raise RouteCandidateValidationError("Every segment must contain a non-empty 'segment_id'")
        seg_id_str = str(seg_id).strip()

        # Check required coordinate endpoints
        for k_coord, min_b, max_b in [
            ("start_latitude", -90.0, 90.0),
            ("start_longitude", -180.0, 180.0),
            ("end_latitude", -90.0, 90.0),
            ("end_longitude", -180.0, 180.0),
        ]:
            if k_coord not in raw_seg or raw_seg[k_coord] is None:
                raise RouteCandidateValidationError(f"Segment '{seg_id_str}' missing required field '{k_coord}'")

        s_lat = _validate_coord("start_latitude", raw_seg["start_latitude"], -90.0, 90.0)
        s_lon = _validate_coord("start_longitude", raw_seg["start_longitude"], -180.0, 180.0)
        e_lat = _validate_coord("end_latitude", raw_seg["end_latitude"], -90.0, 90.0)
        e_lon = _validate_coord("end_longitude", raw_seg["end_longitude"], -180.0, 180.0)

        if "segment_length_km" not in raw_seg or raw_seg["segment_length_km"] is None:
            raise RouteCandidateValidationError(f"Segment '{seg_id_str}' missing 'segment_length_km'")
        length_km = _validate_numeric("segment_length_km", raw_seg["segment_length_km"], min_val=0.0)

        # Exclude blocked segments immediately from graph traversal
        if seg_id_str in blocked_set:
            continue

        u = _coord_to_node_id(s_lat, s_lon)
        v = _coord_to_node_id(e_lat, e_lon)

        r_s_lat = 0.0 if abs(round(s_lat, COORD_ROUND_DECIMALS)) == 0.0 else round(s_lat, COORD_ROUND_DECIMALS)
        r_s_lon = 0.0 if abs(round(s_lon, COORD_ROUND_DECIMALS)) == 0.0 else round(s_lon, COORD_ROUND_DECIMALS)
        r_e_lat = 0.0 if abs(round(e_lat, COORD_ROUND_DECIMALS)) == 0.0 else round(e_lat, COORD_ROUND_DECIMALS)
        r_e_lon = 0.0 if abs(round(e_lon, COORD_ROUND_DECIMALS)) == 0.0 else round(e_lon, COORD_ROUND_DECIMALS)

        node_coords[u] = (r_s_lat, r_s_lon)
        node_coords[v] = (r_e_lat, r_e_lon)

        seg_record = dict(raw_seg)
        seg_record["segment_id"] = seg_id_str
        seg_record["segment_length_km"] = length_km

        if u not in adj:
            adj[u] = []
        if v not in adj:
            adj[v] = []

        # Segments are treated as bidirectional in current normalized schema
        adj[u].append({"neighbor": v, "weight": length_km, "segment_id": seg_id_str, "segment": seg_record})
        adj[v].append({"neighbor": u, "weight": length_km, "segment_id": seg_id_str, "segment": seg_record})

    if segment_count_seen == 0:
        raise RouteCandidateValidationError("Network segments collection is empty; cannot route without segments")

    if not node_coords:
        raise RouteCandidateValidationError(
            "No traversable segments remain in network after excluding blocked segments"
        )

    # Sort adjacency lists deterministically
    for u in adj:
        adj[u].sort(key=lambda edge: (edge["weight"], edge["neighbor"], edge["segment_id"]))

    # 2. Resolve Nearest Nodes via Great-Circle Distance
    source_node = _resolve_nearest_node(orig_lat, orig_lon, node_coords)
    target_node = _resolve_nearest_node(dest_lat, dest_lon, node_coords)

    # 3. Degenerate Origin == Destination Check
    if source_node == target_node:
        n_coord = node_coords[source_node]
        return [
            {
                "route_id": "candidate_001",
                "segment_ids": [],
                "node_ids": [source_node],
                "origin_node": source_node,
                "destination_node": target_node,
                "total_distance_km": 0.0,
                "segment_count": 0,
                "geometry": [[n_coord[0], n_coord[1]]],
                "segments": [],
            }
        ]

    # 4. Yen's K-Shortest Simple Paths Algorithm
    # A holds determined shortest simple paths
    A: List[Dict[str, Any]] = []
    # B holds candidate paths discovered by spur branching
    B: List[Dict[str, Any]] = []

    # Find the initial shortest path
    first_path = _dijkstra_shortest_path(adj, source_node, target_node, banned_edges=set(), banned_nodes=set())
    if first_path is None:
        raise RouteCandidateValidationError(
            f"Origin node '{source_node}' and destination node '{target_node}' are disconnected; no route exists"
        )

    A.append(first_path)

    for i in range(1, k):
        prev_path = A[i - 1]
        prev_nodes = prev_path["nodes"]
        prev_segments = prev_path["segments"]

        # Spur node ranges from the first node up to the second to last node
        for j in range(len(prev_nodes) - 1):
            spur_node = prev_nodes[j]
            root_nodes = prev_nodes[: j + 1]
            root_segments = prev_segments[:j]

            banned_edges: Set[Tuple[str, str, str]] = set()
            banned_nodes: Set[str] = set()

            # Banned edges: for all paths in A that share the identical root path,
            # remove the edge immediately following the spur node
            for p in A:
                p_nodes = p["nodes"]
                p_segs = p["segments"]
                if len(p_nodes) > j and p_nodes[: j + 1] == root_nodes:
                    next_node = p_nodes[j + 1]
                    seg_id = p_segs[j]["segment_id"]
                    banned_edges.add((spur_node, next_node, seg_id))
                    banned_edges.add((next_node, spur_node, seg_id))

            # Banned nodes: all nodes in the root path except the spur node
            for root_node in root_nodes:
                if root_node != spur_node:
                    banned_nodes.add(root_node)

            # Find the spur path from spur_node to target_node
            spur_path = _dijkstra_shortest_path(
                adj,
                spur_node,
                target_node,
                banned_edges=banned_edges,
                banned_nodes=banned_nodes,
            )

            if spur_path is not None:
                total_nodes = root_nodes[:-1] + spur_path["nodes"]
                total_segs = root_segments + spur_path["segments"]
                total_dist = round(sum(s["segment_length_km"] for s in total_segs), 6)

                candidate = {
                    "nodes": total_nodes,
                    "segments": total_segs,
                    "total_distance_km": total_dist,
                }

                cand_segs_tuple = tuple(s["segment_id"] for s in total_segs)
                cand_nodes_tuple = tuple(total_nodes)

                already_in_A = any(
                    tuple(s["segment_id"] for s in p["segments"]) == cand_segs_tuple
                    and tuple(p["nodes"]) == cand_nodes_tuple
                    for p in A
                )
                already_in_B = any(
                    tuple(s["segment_id"] for s in p["segments"]) == cand_segs_tuple
                    and tuple(p["nodes"]) == cand_nodes_tuple
                    for p in B
                )

                if not already_in_A and not already_in_B:
                    B.append(candidate)

        if not B:
            break

        # Select the best candidate from B with deterministic tie-breaking:
        # 1. Total distance
        # 2. Segment count
        # 3. Stable segment IDs sequence
        # 4. Stable node sequence
        B.sort(
            key=lambda c: (
                c["total_distance_km"],
                len(c["segments"]),
                tuple(s["segment_id"] for s in c["segments"]),
                tuple(c["nodes"]),
            )
        )
        best_candidate = B.pop(0)
        A.append(best_candidate)

    # 5. Format Output Contracts
    candidates: List[Dict[str, Any]] = []
    for idx, path in enumerate(A, start=1):
        p_nodes = path["nodes"]
        p_segs = path["segments"]

        geometry = [[node_coords[n][0], node_coords[n][1]] for n in p_nodes]

        candidate_record = {
            "route_id": f"candidate_{idx:03d}",
            "segment_ids": [s["segment_id"] for s in p_segs],
            "node_ids": p_nodes,
            "origin_node": source_node,
            "destination_node": target_node,
            "total_distance_km": path["total_distance_km"],
            "segment_count": len(p_segs),
            "geometry": geometry,
            "segments": p_segs,
        }
        candidates.append(candidate_record)

    return candidates
