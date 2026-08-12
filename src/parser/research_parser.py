"""Deterministic, layout-aware semantic parser for research-paper PDFs.

This module deliberately keeps extraction, layout ordering, classification, and
document assembly separate.  It does not use an LLM; ambiguous PDF artefacts
remain visible in the output through their source bounding boxes.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

try:
    import pymupdf
except ImportError:  # pragma: no cover - exercised only without dependency
    pymupdf = None


HEADING = re.compile(r"^(?:(?P<number>\d+(?:\.\d+)*)\.?\s+)?(?P<title>[A-Z][\w &,:;()\-]{1,100})$")
CAPTION = re.compile(r"^(?P<kind>fig(?:ure)?|table)\.?\s*(?P<number>\d+[\w.-]*)\s*[:.]?\s*(?P<caption>.*)$", re.I)
EQUATION_NUMBER = re.compile(r"\((?P<number>\d+(?:\.\d+)*)\)\s*$")
REFERENCE = re.compile(r"^\s*\[(?P<key>[^]]+)\]\s*(?P<text>.+)$")
DOI = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
ARXIV = re.compile(r"\barXiv:\s*(?P<id>\d{4}\.\d{4,5}(?:v\d+)?)", re.I)
CROSS_REFERENCE = re.compile(r"\b(?:Fig(?:ure)?|Table|Eq(?:uation)?|Section|Sec\.)\s*\(?\d+(?:\.\d+)*\)?|\[\d+(?:\s*,\s*\d+)*\]")
SPECIAL_BLOCK = re.compile(r"^(theorem|definition|proof|remark|example|algorithm)\b", re.I)


def _bbox(rect: Any) -> dict[str, float]:
    return {"x0": round(rect[0], 2), "y0": round(rect[1], 2), "x1": round(rect[2], 2), "y1": round(rect[3], 2)}


def extract_layout(pdf_path: str | Path) -> list[dict[str, Any]]:
    """Extract text/image blocks with page numbers and PDF-space bounding boxes."""
    if pymupdf is None:
        raise ImportError("pymupdf is required for layout-aware research parsing")
    document = pymupdf.open(str(pdf_path))
    pages: list[dict[str, Any]] = []
    try:
        for page_number, page in enumerate(document, start=1):
            page_data = page.get_text("dict")
            blocks: list[dict[str, Any]] = []
            for index, block in enumerate(page_data["blocks"]):
                box = _bbox(block["bbox"])
                if block["type"] == 1:
                    blocks.append({"source_index": index, "kind": "image", "text": "", "page": page_number, "bbox": box})
                    continue
                lines = block.get("lines", [])
                text = "\n".join("".join(span["text"] for span in line["spans"]) for line in lines).strip()
                if not text:
                    continue
                sizes = [span["size"] for line in lines for span in line["spans"]]
                blocks.append({"source_index": index, "kind": "text", "text": text, "page": page_number, "bbox": box,
                               "font_size": round(max(sizes, default=0), 2)})
            tables = []
            try:
                for table_index, table in enumerate(page.find_tables().tables, start=1):
                    rows = table.extract()
                    tables.append({"id": f"table-{page_number}-{table_index}", "page": page_number,
                                   "bbox": _bbox(table.bbox), "headers": rows[0] if rows else [],
                                   "rows": rows[1:] if len(rows) > 1 else [], "footnotes": []})
            except Exception:
                # Vector drawings and malformed PDFs need not prevent text parsing.
                pass
            pages.append({"number": page_number, "width": round(page.rect.width, 2), "height": round(page.rect.height, 2),
                          "blocks": _reading_order(blocks, page.rect.width), "tables": tables})
    finally:
        document.close()
    return pages


def _reading_order(blocks: list[dict[str, Any]], width: float) -> list[dict[str, Any]]:
    """Order blocks by full-width material then left/right columns.

    A page is considered columnar only when both halves have at least three
    text blocks.  This prevents authors/titles on ordinary pages becoming a
    fake right column.
    """
    text = [b for b in blocks if b["kind"] == "text"]
    midpoint = width / 2
    left = [b for b in text if b["bbox"]["x0"] < midpoint and b["bbox"]["x1"] <= midpoint + width * .08]
    right = [b for b in text if b["bbox"]["x0"] >= midpoint - width * .08]
    if len(left) < 3 or len(right) < 3:
        return sorted(blocks, key=lambda b: (b["bbox"]["y0"], b["bbox"]["x0"]))
    spanning = [b for b in blocks if b not in left and b not in right]
    top = [b for b in spanning if b["bbox"]["y0"] < min(left[0]["bbox"]["y0"], right[0]["bbox"]["y0"])]
    rest = [b for b in spanning if b not in top]
    key = lambda b: (b["bbox"]["y0"], b["bbox"]["x0"])
    return sorted(top, key=key) + sorted(left, key=key) + sorted(right, key=key) + sorted(rest, key=key)


def _classify(block: dict[str, Any]) -> str:
    text = block["text"].strip()
    if block["kind"] == "image":
        return "figure"
    if CAPTION.match(text):
        return "figure_caption" if CAPTION.match(text).group("kind").lower().startswith("fig") else "table_caption"
    if SPECIAL_BLOCK.match(text):
        return SPECIAL_BLOCK.match(text).group(1).lower()
    if EQUATION_NUMBER.search(text) and (any(char in text for char in "=∑∫√") or len(text.split()) < 20):
        return "equation"
    if re.match(r"^(?:[-•‣]|\d+[.)])\s+", text):
        return "numbered_list" if re.match(r"^\d+", text) else "bullet_list"
    return "paragraph"


def _cross_references(text: str) -> list[str]:
    return CROSS_REFERENCE.findall(text)


def _block_record(block: dict[str, Any], block_id: str) -> dict[str, Any]:
    text = block["text"]
    record = {"id": block_id, "type": _classify(block), "text": text, "page": block["page"], "bbox": block["bbox"], "cross_references": _cross_references(text)}
    equation = EQUATION_NUMBER.search(text)
    if record["type"] == "equation":
        record["equation_number"] = equation.group("number") if equation else None
    return record


def _metadata(first_page: Iterable[dict[str, Any]]) -> dict[str, Any]:
    text_blocks = [b for b in first_page if b["kind"] == "text"]
    title = max(text_blocks, key=lambda b: b.get("font_size", 0), default={"text": ""})["text"]
    all_text = "\n".join(b["text"] for b in text_blocks)
    abstract_index = next((i for i, b in enumerate(text_blocks) if b["text"].strip().lower() == "abstract"), None)
    preamble = text_blocks[:abstract_index] if abstract_index is not None else text_blocks[:6]
    author_lines = [b["text"] for b in preamble if re.search(r"\b[A-Z][a-z]+\b", b["text"]) and b["text"] != title]
    affiliations = [line for line in author_lines if re.search(r"University|Department|Institute|Laboratory|School|@", line, re.I)]
    authors = [line for line in author_lines if line not in affiliations]
    return {"title": title, "authors": authors, "affiliations": affiliations, "doi": DOI.findall(all_text),
            "arxiv_id": [m.group("id") for m in ARXIV.finditer(all_text)], "publication_information": []}


def parse_research_paper(pdf_path: str | Path) -> dict[str, Any]:
    """Return the hierarchical semantic representation of one research paper."""
    pages = extract_layout(pdf_path)
    metadata = _metadata(pages[0]["blocks"]) if pages else {}
    root_sections: list[dict[str, Any]] = []
    stack: list[dict[str, Any]] = []
    figures: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []
    abstract: dict[str, Any] | None = None
    in_references = False
    block_number = 0

    for page in pages:
        tables.extend(page["tables"])
        for source in page["blocks"]:
            text = source["text"].strip()
            heading = HEADING.match(text) if source["kind"] == "text" else None
            is_heading = bool(
                heading and (heading.group("number") or text.lower() in {"abstract", "references", "keywords"})
            )
            if is_heading:
                title, number = heading.group("title"), heading.group("number")
                if title.lower() == "abstract":
                    abstract = {"page": source["page"], "bbox": source["bbox"], "blocks": []}
                    continue
                if title.lower() == "references":
                    in_references = True
                    stack.clear()
                    continue
                level = number.count(".") + 1 if number else 1
                section = {"id": f"section-{number or len(root_sections) + 1}", "title": title, "number": number, "level": level,
                           "page": source["page"], "bbox": source["bbox"], "blocks": [], "subsections": []}
                while stack and stack[-1]["level"] >= level:
                    stack.pop()
                (stack[-1]["subsections"] if stack else root_sections).append(section)
                stack.append(section)
                continue
            block_number += 1
            record = _block_record(source, f"block-{block_number}")
            if in_references:
                match = REFERENCE.match(text)
                reference_text = match.group("text") if match else text
                references.append({"id": match.group("key") if match else f"raw-{len(references) + 1}", "raw": reference_text,
                                   "page": source["page"], "bbox": source["bbox"], "doi": DOI.findall(reference_text),
                                   "url": re.findall(r"https?://\S+", reference_text)})
                continue
            target = abstract["blocks"] if abstract is not None and not stack else (stack[-1]["blocks"] if stack else [])
            target.append(record)
            caption = CAPTION.match(text)
            if caption:
                item = {"id": f"{caption.group('kind').lower()}-{caption.group('number')}", "number": caption.group("number"), "caption": caption.group("caption"),
                        "page": source["page"], "bbox": source["bbox"], "references": _cross_references(text)}
                if record["type"] == "figure_caption":
                    figures.append(item)
                else:
                    nearest_table = next((table for table in reversed(tables) if table["page"] == source["page"]), None)
                    if nearest_table is not None:
                        nearest_table["caption"] = item["caption"]
                        nearest_table["number"] = item["number"]
                    else:
                        tables.append(item)

    return {"document": {"metadata": metadata, "abstract": abstract, "sections": root_sections, "figures": figures,
                         "tables": tables, "references": references, "source": {"file": str(pdf_path), "page_count": len(pages)}}}
