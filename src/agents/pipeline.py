"""pipeline.py

Orchestrator for the Paper Lens agentic workflow.

Sequential pipeline:
  1. TermExtractorAgent  — finds domain-specific AI/ML terms in the paper
  2. TermExplainerAgent  — explains each term in context + generally

Monitoring outputs (written to src/outputs/ after each agent completes):
  extracted_terms_<pdf_name>.json  — raw Agent 1 output
  explained_terms_<pdf_name>.json  — Agent 2 output (final glossary)

Usage:
    from agents.pipeline import run_pipeline

    result = run_pipeline(parsed_paper_json, pdf_name="mae")
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.agents.term_extractor import TermExtractorAgent
from src.agents.term_explainer import TermExplainerAgent

# Resolve the outputs directory relative to this file's location:
# src/agents/../outputs → src/outputs
_OUTPUTS_DIR = Path(__file__).parent.parent / "outputs"


def _save_monitoring(data: Any, filename: str) -> None:
    """Saves agent output to src/outputs/<filename> for monitoring."""
    _OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    path = _OUTPUTS_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"[pipeline] Monitoring output saved -> {path}")


def run_pipeline(
    paper_sections: List[Dict[str, Any]],
    pdf_name: Optional[str] = "paper",
) -> Dict[str, Any]:
    """
    Runs the full two-agent pipeline on a parsed paper JSON.

    Args:
        paper_sections: Output of parse_pdf_to_json() — nested section list.
        pdf_name: Stem of the original PDF filename (used for monitoring files).

    Returns:
        dict with keys:
          - paper_title (str)
          - term_count  (int)
          - glossary    (list of explained term dicts)
    """
    # Resolve paper title from the Preamble section
    paper_title = "Unknown Paper"
    for sec in paper_sections:
        if sec.get("title") == "Preamble" and sec.get("content"):
            paper_title = sec["content"]
            break

    # --- Agent 1: extract terms ---
    print(f"[pipeline] Running TermExtractorAgent for '{pdf_name}'...")
    extractor = TermExtractorAgent()
    extracted_terms = extractor.run(paper_sections)

    # Monitoring: save Agent 1 raw output
    _save_monitoring(extracted_terms, f"extracted_terms_{pdf_name}.json")

    # --- Agent 2: explain terms ---
    print(f"[pipeline] Running TermExplainerAgent for '{pdf_name}' ({len(extracted_terms)} terms)...")
    explainer = TermExplainerAgent()
    glossary = explainer.run(extracted_terms, paper_sections)

    # Monitoring: save Agent 2 final output
    _save_monitoring(glossary, f"explained_terms_{pdf_name}.json")

    return {
        "paper_title": paper_title,
        "term_count": len(glossary),
        "glossary": glossary,
    }
