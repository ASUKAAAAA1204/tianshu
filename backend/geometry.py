"""Small dependency-free planar geometry helpers for offline operation.

Coordinates are treated as longitude/latitude pairs over the local demo area.
For production PostGIS, this module is the compatibility fallback and should be
replaced by the database spatial functions through the repository adapter.
"""

from __future__ import annotations

from typing import Iterable, Sequence


Point = tuple[float, float]
EPSILON = 1e-10


def _cross(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a: Point, b: Point, p: Point) -> bool:
    return (
        abs(_cross(a, b, p)) <= EPSILON
        and min(a[0], b[0]) - EPSILON <= p[0] <= max(a[0], b[0]) + EPSILON
        and min(a[1], b[1]) - EPSILON <= p[1] <= max(a[1], b[1]) + EPSILON
    )


def segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    """Return whether two closed line segments touch or cross."""
    ab_c, ab_d = _cross(a, b, c), _cross(a, b, d)
    cd_a, cd_b = _cross(c, d, a), _cross(c, d, b)
    if ((ab_c > EPSILON and ab_d < -EPSILON) or (ab_c < -EPSILON and ab_d > EPSILON)) and ((cd_a > EPSILON and cd_b < -EPSILON) or (cd_a < -EPSILON and cd_b > EPSILON)):
        return True
    return _on_segment(a, b, c) or _on_segment(a, b, d) or _on_segment(c, d, a) or _on_segment(c, d, b)


def point_in_ring(point: Point, ring: Sequence[Sequence[float]]) -> bool:
    """Ray-casting containment; points on the boundary count as inside."""
    if len(ring) < 4:
        return False
    inside = False
    previous = (float(ring[-1][0]), float(ring[-1][1]))
    for raw in ring:
        current = (float(raw[0]), float(raw[1]))
        if _on_segment(previous, current, point):
            return True
        if (current[1] > point[1]) != (previous[1] > point[1]):
            x_at_y = (previous[0] - current[0]) * (point[1] - current[1]) / (previous[1] - current[1]) + current[0]
            if point[0] < x_at_y:
                inside = not inside
        previous = current
    return inside


def segment_intersects_polygon(start: Point, end: Point, geometry: dict) -> bool:
    """Return whether a segment touches or passes through a Polygon.

    The first ring is the exterior; subsequent rings are holes. A segment is
    considered intersecting when it touches any ring or has a point inside the
    exterior but not inside a hole.
    """
    if geometry.get("type") != "Polygon":
        return False
    rings = geometry.get("coordinates") or []
    if not rings:
        return False
    for ring in rings:
        for index in range(len(ring) - 1):
            edge_start = (float(ring[index][0]), float(ring[index][1]))
            edge_end = (float(ring[index + 1][0]), float(ring[index + 1][1]))
            if segments_intersect(start, end, edge_start, edge_end):
                return True
    if not point_in_ring(start, rings[0]) and not point_in_ring(end, rings[0]):
        return False
    if any(point_in_ring(start, hole) or point_in_ring(end, hole) for hole in rings[1:]):
        return False
    return True
