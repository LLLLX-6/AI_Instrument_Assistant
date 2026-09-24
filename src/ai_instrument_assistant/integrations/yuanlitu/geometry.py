from __future__ import annotations

import math
from dataclasses import dataclass

from .dto import PinDto, WireDto
from .errors import YuanlituMappingError


@dataclass(frozen=True, slots=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class ConnectivityResult:
    wire_networks: dict[str, str]
    pin_networks: dict[tuple[str, str], str | None]
    network_wires: dict[str, tuple[str, ...]]


class _UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, first: int, second: int) -> None:
        left, right = self.find(first), self.find(second)
        if left != right:
            self.parent[max(left, right)] = min(left, right)


def derive_connectivity(
    wires: tuple[WireDto, ...],
    pins: tuple[PinDto, ...],
    tolerance: float,
) -> ConnectivityResult:
    if not math.isfinite(tolerance) or tolerance <= 0:
        raise YuanlituMappingError("coordinate tolerance must be positive and finite")
    if len({wire.provider_ref for wire in wires}) != len(wires):
        raise YuanlituMappingError("wire provider references must be unique")
    union = _UnionFind(len(wires))
    geometries = tuple(_geometry(wire) for wire in wires)
    for left in range(len(wires)):
        for right in range(left + 1, len(wires)):
            if _wires_connect(geometries[left], geometries[right], tolerance):
                union.union(left, right)

    touched_by_pin: dict[tuple[str, str], list[int]] = {}
    for pin in pins:
        key = (pin.component_ref, pin.number)
        if key in touched_by_pin:
            raise YuanlituMappingError("pin provider identity must be unique")
        touched = [] if pin.no_connected else [
            index for index, (_, segments) in enumerate(geometries)
            if any(_point_on_segment(Point(pin.x, pin.y), segment, tolerance) for segment in segments)
        ]
        for index in touched[1:]:
            union.union(touched[0], index)
        touched_by_pin[key] = touched

    groups: dict[int, list[str]] = {}
    for index, wire in enumerate(wires):
        groups.setdefault(union.find(index), []).append(wire.provider_ref)
    ordered = sorted((tuple(sorted(values)), root) for root, values in groups.items())
    network_by_root = {root: f"network-{index + 1}" for index, (_, root) in enumerate(ordered)}
    wire_networks = {
        wire.provider_ref: network_by_root[union.find(index)]
        for index, wire in enumerate(wires)
    }
    pin_networks = {
        key: None if not touched else network_by_root[union.find(touched[0])]
        for key, touched in touched_by_pin.items()
    }
    network_wires = {
        network_by_root[root]: values for values, root in ordered
    }
    return ConnectivityResult(wire_networks, pin_networks, network_wires)


Segment = tuple[Point, Point]


def _geometry(wire: WireDto) -> tuple[tuple[Point, ...], tuple[Segment, ...]]:
    points = tuple(Point(wire.line[index], wire.line[index + 1]) for index in range(0, len(wire.line), 2))
    segments = tuple((points[index], points[index + 1]) for index in range(len(points) - 1))
    return points, segments


def _wires_connect(
    first: tuple[tuple[Point, ...], tuple[Segment, ...]],
    second: tuple[tuple[Point, ...], tuple[Segment, ...]],
    tolerance: float,
) -> bool:
    first_points, first_segments = first
    second_points, second_segments = second
    if any(_same(left, right, tolerance) for left in first_points for right in second_points):
        return True
    if any(_point_on_segment(point, segment, tolerance) for point in first_points for segment in second_segments):
        return True
    if any(_point_on_segment(point, segment, tolerance) for point in second_points for segment in first_segments):
        return True
    return any(
        _collinear_overlap(left, right, tolerance)
        for left in first_segments for right in second_segments
    )


def _same(first: Point, second: Point, tolerance: float) -> bool:
    return math.hypot(first.x - second.x, first.y - second.y) <= tolerance


def _point_on_segment(point: Point, segment: Segment, tolerance: float) -> bool:
    start, end = segment
    dx, dy = end.x - start.x, end.y - start.y
    length = math.hypot(dx, dy)
    if length <= tolerance:
        return _same(point, start, tolerance)
    distance = abs(dx * (start.y - point.y) - (start.x - point.x) * dy) / length
    if distance > tolerance:
        return False
    projection = ((point.x - start.x) * dx + (point.y - start.y) * dy) / (length * length)
    return -tolerance / length <= projection <= 1 + tolerance / length


def _collinear_overlap(first: Segment, second: Segment, tolerance: float) -> bool:
    if not _point_on_infinite_line(second[0], first, tolerance) or not _point_on_infinite_line(second[1], first, tolerance):
        return False
    dx, dy = first[1].x - first[0].x, first[1].y - first[0].y
    if abs(dx) >= abs(dy):
        left = sorted((first[0].x, first[1].x))
        right = sorted((second[0].x, second[1].x))
    else:
        left = sorted((first[0].y, first[1].y))
        right = sorted((second[0].y, second[1].y))
    return max(left[0], right[0]) <= min(left[1], right[1]) + tolerance


def _point_on_infinite_line(point: Point, segment: Segment, tolerance: float) -> bool:
    start, end = segment
    length = math.hypot(end.x - start.x, end.y - start.y)
    if length <= tolerance:
        return _same(point, start, tolerance)
    return abs((end.x - start.x) * (start.y - point.y) - (start.x - point.x) * (end.y - start.y)) / length <= tolerance
