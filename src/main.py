"""main.py

Entry point for the Paper Lens pipeline.

Full workflow (CLI):
  1. Parse PDF → structured JSON + save to outputs/<name>.json
  2. Run agentic pipeline:
       Agent 1 — extract AI/ML-specific terms (saved to outputs/extracted_terms_<name>.json)
       Agent 2 — explain each term in context + generally (saved to outputs/explained_terms_<name>.json)
  3. Persist sections (with extracted_terms) to SQLite database

Usage:
    python main.py <pdf_path> [--out-dir outputs] [--db data]

Example:
    python main.py papers/mae.pdf --out-dir outputs --db data
"""

import argparse
import json
from pathlib import Path

from parser.pdf_parser import parse_pdf_to_json
from agents.pipeline import run_pipeline
from database.repository import init_db, clear_sections, save_document_sections

# Anchor all default paths to src/ (this file's directory)
_SRC_DIR = Path(__file__).parent


def _collect_all_titles(sections: list, titles: set = None) -> set:
    """Recursively collect every section title from the nested hierarchy."""
    if titles is None:
        titles = set()
    for sec in sections:
        titles.add(sec.get("title", ""))
        _collect_all_titles(sec.get("subsections", []), titles)
    return titles


def main():
    parser = argparse.ArgumentParser(
        description="Paper Lens — Parse a research PDF and extract AI/ML term glossary."
    )
    parser.add_argument("pdf", type=str, help="Path to the PDF file to process")
    parser.add_argument(
        "--out-dir",
        type=str,
        default=str(_SRC_DIR / "outputs"),
        help="Directory for JSON outputs (default: src/outputs)",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=str(_SRC_DIR / "data"),
        help="Directory for the SQLite database (default: src/data)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run even if outputs already exist",
    )

    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    out_dir = Path(args.out_dir)
    db_dir = Path(args.db)
    pdf_name = pdf_path.stem

    if not pdf_path.exists():
        print(f"Error: PDF file '{pdf_path}' does not exist.")
        return

    # ── Already-done check ────────────────────────────────────────────────────
    # pipeline.py always writes monitoring files to _SRC_DIR/outputs/
    explained_path = _SRC_DIR / "outputs" / f"explained_terms_{pdf_name}.json"
    if explained_path.exists() and not args.force:
        print(
            f"Already processed: '{pdf_name}'\n"
            f"  Found: {explained_path}\n"
            f"  Use --force to re-run and overwrite existing outputs."
        )
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    db_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / f"{pdf_name}.json"
    db_path = db_dir / f"{pdf_name}.db"

    # ── Step 1: Parse PDF ─────────────────────────────────────────────────────
    print(f"\n[1/3] Parsing '{pdf_path}'...")
    sections = parse_pdf_to_json(pdf_path, json_path)
    print(f"      Parsed {len(sections)} top-level sections -> {json_path}")

    # ── Step 2: Run agentic pipeline ──────────────────────────────────────────
    print(f"\n[2/3] Running agentic pipeline...")
    result = run_pipeline(sections, pdf_name=pdf_name)
    print(
        f"      Done - {result['term_count']} terms extracted and explained.\n"
        f"      Paper: {result['paper_title']}"
    )

    # ── Step 3: Persist to SQLite ─────────────────────────────────────────────
    # Map the full glossary to EVERY section title (top-level + subsections)
    # so every row in the DB has extracted_terms populated.
    print(f"\n[3/3] Saving to database '{db_path}'...")
    all_titles = _collect_all_titles(sections)
    terms_by_title = {title: result["glossary"] for title in all_titles}

    SessionLocal = init_db(db_path)
    with SessionLocal() as session:
        clear_sections(session)
        save_document_sections(session, sections, terms_by_title=terms_by_title)
    print(f"      Database saved -> {db_path}")
    print(f"      extracted_terms stored on {len(all_titles)} section rows")

    # -- Summary ---------------------------------------------------------------
    print(
        f"\n" +
        f"+--------------------------------------------------+\n" +
        f"|  Paper Lens - Complete                          |\n" +
        f"+--------------------------------------------------+\n" +
        f"|  PDF parsed      : {json_path}\n" +
        f"|  Terms extracted : {result['term_count']}\n" +
        f"|  Agent 1 output  : {out_dir}/extracted_terms_{pdf_name}.json\n" +
        f"|  Agent 2 output  : {out_dir}/explained_terms_{pdf_name}.json\n" +
        f"|  Database        : {db_path}\n" +
        f"+--------------------------------------------------+"
    )


if __name__ == "__main__":
    main()
