"""pipeline.py

Orchestrator for the Paper Lens agentic workflow.

Sequential pipeline:
  1. TermExtractorAgent  — finds domain-specific AI/ML terms in the paper
  2. TermExplainerAgent  — explains each term in context + generally

Includes smart result caching (prevents redundant LLM calls when a paper was already processed)
and monitoring logger trace tracking (request_id, timestamp, latency, tokens, level, errors).
"""

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.agents.term_extractor import TermExtractorAgent
from src.agents.term_explainer import TermExplainerAgent
from src.monitoring.logger import monitor_logger

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
    request_id: Optional[str] = None,
    force_rerun: bool = False,
) -> Dict[str, Any]:
    """
    Runs the full two-agent pipeline on a parsed paper JSON with smart output caching.

    Args:
        paper_sections: Output of parse_pdf_to_json() — nested section list.
        pdf_name: Stem of the original PDF filename (used for monitoring files).
        request_id: Unique correlation ID for monitoring traces across sub-agents.
        force_rerun: If True, bypasses cached outputs and re-executes agents.

    Returns:
        dict with keys:
          - request_id  (str)
          - paper_title (str)
          - term_count  (int)
          - glossary    (list of explained term dicts)
          - cached      (bool)
    """
    t0 = time.time()
    req_id = request_id or f"req_{uuid.uuid4().hex[:10]}"
    error_msg = None
    glossary = []
    is_cached = False

    # Resolve paper title from the Preamble section
    paper_title = "Unknown Paper"
    for sec in paper_sections:
        if sec.get("title") == "Preamble" and sec.get("content"):
            paper_title = sec["content"]
            break

    # --- Cache Check ---------------------------------------------------------
    explained_path = _OUTPUTS_DIR / f"explained_terms_{pdf_name}.json"
    if explained_path.exists() and not force_rerun:
        try:
            print(f"[pipeline] [{req_id}] Reusing cached analysis for '{pdf_name}' -> {explained_path}")
            with open(explained_path, "r", encoding="utf-8") as f:
                glossary = json.load(f)

            is_cached = True
            latency_ms = (time.time() - t0) * 1000.0

            monitor_logger.log(
                level="INFO",
                endpoint="run_pipeline.cached",
                agent_invoked="CacheManager",
                input_data={"pdf_name": pdf_name, "section_count": len(paper_sections), "cached": True},
                output_data={"paper_title": paper_title, "term_count": len(glossary)},
                latency_ms=latency_ms,
                tokens_used={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                errors=None,
                request_id=req_id,
            )

            return {
                "request_id": req_id,
                "paper_title": paper_title,
                "term_count": len(glossary),
                "glossary": glossary,
                "cached": True,
            }
        except Exception as cache_err:
            print(f"[pipeline] Warning: Failed to read cache file ({cache_err}). Re-running pipeline...")

    try:
        # --- Agent 1: extract terms ---
        print(f"[pipeline] [{req_id}] Running TermExtractorAgent for '{pdf_name}'...")
        extractor = TermExtractorAgent()
        extracted_terms = extractor.run(paper_sections, request_id=req_id)

        # Save Agent 1 raw output
        _save_monitoring(extracted_terms, f"extracted_terms_{pdf_name}.json")

        # --- Agent 2: explain terms ---
        print(f"[pipeline] [{req_id}] Running TermExplainerAgent for '{pdf_name}' ({len(extracted_terms)} terms)...")
        explainer = TermExplainerAgent()
        glossary = explainer.run(extracted_terms, paper_sections, request_id=req_id)

        # Save Agent 2 final output
        _save_monitoring(glossary, f"explained_terms_{pdf_name}.json")

    except Exception as err:
        error_msg = str(err)
        raise err
    finally:
        latency_ms = (time.time() - t0) * 1000.0
        monitor_logger.log(
            level="ERROR" if error_msg else "INFO",
            endpoint="run_pipeline",
            agent_invoked="PipelineOrchestrator",
            input_data={"pdf_name": pdf_name, "section_count": len(paper_sections), "cached": is_cached},
            output_data={"paper_title": paper_title, "term_count": len(glossary)},
            latency_ms=latency_ms,
            errors=error_msg,
            request_id=req_id,
        )

    return {
        "request_id": req_id,
        "paper_title": paper_title,
        "term_count": len(glossary),
        "glossary": glossary,
        "cached": False,
    }
