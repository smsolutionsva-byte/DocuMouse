"""Geometry helpers over engine text lines (normalised 0..1 coordinates)."""

from __future__ import annotations

from ..processing.types import TextLine


def height(line: TextLine) -> float:
    return max(1e-4, line.bbox[3] - line.bbox[1])


def center_y(line: TextLine) -> float:
    return (line.bbox[1] + line.bbox[3]) / 2


def same_row(a: TextLine, b: TextLine) -> bool:
    if a.page != b.page:
        return False
    overlap = min(a.bbox[3], b.bbox[3]) - max(a.bbox[1], b.bbox[1])
    return overlap >= 0.5 * min(height(a), height(b))


def x_overlap(a: TextLine, b: TextLine) -> float:
    return max(0.0, min(a.bbox[2], b.bbox[2]) - max(a.bbox[0], b.bbox[0]))


def right_neighbours(line: TextLine, lines: list[TextLine]) -> list[TextLine]:
    """Lines on the same visual row, to the right, nearest first."""
    out = [o for o in lines if o is not line and same_row(line, o) and o.bbox[0] >= line.bbox[2] - 0.005]
    return sorted(out, key=lambda o: o.bbox[0])


def row_of(line: TextLine, lines: list[TextLine]) -> list[TextLine]:
    return sorted([o for o in lines if o is line or same_row(line, o)], key=lambda o: o.bbox[0])


def lines_below(line: TextLine, lines: list[TextLine], *, max_gap_lines: float = 2.5) -> list[TextLine]:
    """Lines directly underneath (horizontally overlapping), nearest first."""
    h = height(line)
    out = []
    for o in lines:
        if o is line or o.page != line.page:
            continue
        gap = o.bbox[1] - line.bbox[3]
        if -0.3 * h <= gap <= max_gap_lines * h and x_overlap(line, o) > 0 and not same_row(line, o):
            out.append(o)
    return sorted(out, key=lambda o: o.bbox[1])


def union_bbox(lines: list[TextLine]) -> list[float]:
    return [
        min(ln.bbox[0] for ln in lines),
        min(ln.bbox[1] for ln in lines),
        max(ln.bbox[2] for ln in lines),
        max(ln.bbox[3] for ln in lines),
    ]


def inside(line: TextLine, bbox: list[float], page: int, tolerance: float = 0.01) -> bool:
    cx = (line.bbox[0] + line.bbox[2]) / 2
    cy = center_y(line)
    return (
        line.page == page
        and bbox[0] - tolerance <= cx <= bbox[2] + tolerance
        and bbox[1] - tolerance <= cy <= bbox[3] + tolerance
    )
