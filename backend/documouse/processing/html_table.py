"""Parse the HTML tables PP-StructureV3 emits into a plain grid."""

from __future__ import annotations

from html.parser import HTMLParser


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[tuple[str, int, int, bool]]] = []  # (text, rowspan, colspan, is_header)
        self._row: list[tuple[str, int, int, bool]] | None = None
        self._cell: list[str] | None = None
        self._span = (1, 1)
        self._is_header = False
        self._in_thead = False
        self.thead_rows = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "thead":
            self._in_thead = True
        elif tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
            self._span = (_int(a.get("rowspan")), _int(a.get("colspan")))
            self._is_header = tag == "th" or self._in_thead
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag):
        if tag == "thead":
            self._in_thead = False
        elif tag in ("td", "th") and self._row is not None and self._cell is not None:
            text = " ".join("".join(self._cell).split())
            self._row.append((text, *self._span, self._is_header))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._in_thead:
                self.thead_rows += 1
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _int(value: str | None) -> int:
    try:
        return max(1, int(value or 1))
    except ValueError:
        return 1


def parse_html_table(html: str) -> tuple[list[list[str]], int]:
    """Return ``(grid, header_rows)``.

    Row/col spans are resolved so every row has the same width. A spanned cell's
    text is kept in its top-left position only; covered positions are empty, which
    keeps the grid honest about what was actually printed.
    """
    parser = _TableParser()
    parser.feed(html)
    occupied: dict[tuple[int, int], str] = {}
    width = 0
    header_rows = parser.thead_rows
    for r, row in enumerate(parser.rows):
        c = 0
        for text, rowspan, colspan, is_header in row:
            while (r, c) in occupied:
                c += 1
            for dr in range(rowspan):
                for dc in range(colspan):
                    occupied[(r + dr, c + dc)] = text if (dr == 0 and dc == 0) else ""
            c += colspan
            width = max(width, c)
        if not parser.thead_rows and row and all(cell[3] for cell in row) and r == header_rows:
            header_rows += 1
    height = max((r for r, _ in occupied), default=-1) + 1
    grid = [[occupied.get((r, c), "") for c in range(width)] for r in range(height)]
    # Drop rows that are completely empty (span artefacts).
    grid = [row for row in grid if any(cell.strip() for cell in row)]
    return grid, header_rows
