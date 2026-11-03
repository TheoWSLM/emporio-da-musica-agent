"""Turns the store manual PDF into an ordered list of layout elements (headings, paragraphs, tables).

Structure comes from the layout, not from regexes over the text: section titles are 14pt bold,
subsection titles 12pt bold, body text 10pt. Tables are extracted with PyMuPDF and kept whole as
Markdown; the text lines inside a table's bounding box are dropped so nothing is duplicated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import pymupdf

SECTION_SIZE = 13.5
SUBSECTION_SIZE = 11.5
MIN_BODY_SIZE = 9.0
HEADER_MARGIN = 70.0
FOOTER_MARGIN = 60.0
_FOOTER = re.compile(r"^Página \d+$")
_BULLET = re.compile(r"^\u2022\s*")


class Kind(StrEnum):
    SECTION = "section"
    SUBSECTION = "subsection"
    TEXT = "text"
    TABLE = "table"


@dataclass(frozen=True)
class Element:
    kind: Kind
    text: str


def _inside(
    bbox: tuple[float, float, float, float], box: tuple[float, float, float, float]
) -> bool:
    x0, y0, x1, y1 = bbox
    return x0 >= box[0] - 1 and y0 >= box[1] - 1 and x1 <= box[2] + 1 and y1 <= box[3] + 1


def _table_markdown(markdown: str) -> str:
    return markdown.replace("<br>", " ").replace("\u200b", "").strip()


def parse_pdf(path: Path, skip_pages: int = 1) -> list[Element]:
    """skip_pages: the cover page carries no policy content."""
    elements: list[Element] = []
    with pymupdf.open(path) as document:  # type: ignore[no-untyped-call]
        for page_number, page in enumerate(document):
            if page_number < skip_pages:
                continue
            tables = [
                (tuple(t.bbox), _table_markdown(t.to_markdown())) for t in page.find_tables().tables
            ]
            pending_tables = sorted(tables, key=lambda t: t[0][1])
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    text = (
                        "".join(span["text"] for span in line["spans"])
                        .replace("\u200b", "")
                        .strip()
                    )
                    bbox = tuple(line["bbox"])
                    in_margin = (
                        bbox[3] < HEADER_MARGIN or bbox[1] > page.rect.height - FOOTER_MARGIN
                    )
                    if not text or in_margin:
                        continue  # running header / footer
                    while pending_tables and pending_tables[0][0][1] <= bbox[1]:
                        elements.append(Element(Kind.TABLE, pending_tables.pop(0)[1]))
                    if any(_inside(bbox, table_box) for table_box, _ in tables):
                        continue
                    size = max(span["size"] for span in line["spans"])
                    if size < MIN_BODY_SIZE or _FOOTER.match(text):
                        continue
                    if size >= SECTION_SIZE:
                        elements.append(Element(Kind.SECTION, text))
                    elif size >= SUBSECTION_SIZE:
                        elements.append(Element(Kind.SUBSECTION, text))
                    else:
                        elements.append(
                            Element(Kind.TEXT, _BULLET.sub("- ", text).replace("-  ", "- "))
                        )
            elements.extend(Element(Kind.TABLE, markdown) for _, markdown in pending_tables)
    return elements
