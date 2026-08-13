"""term_extractor.py

Agent 1 — AI/ML Term Extractor.

Extracts domain-specific AI/ML terms from a research paper using a lightweight,
token-optimized summary input. Sentences containing occurrences are matched
directly in Python to eliminate completion token bloat and prevent Groq API rate limits.
"""

import json
import os
import re
import time
from typing import Any, Dict, List

from groq import Groq
from dotenv import load_dotenv

load_dotenv()

GROQ_PRIMARY_MODEL = "llama-3.3-70b-versatile"
GROQ_FALLBACK_MODEL = "llama-3.1-8b-instant"

SYSTEM_PROMPT = """\
You are an expert AI/ML researcher and technical writer. Read the research paper summary
and extract domain-specific terminology that is significant to THIS paper's specific contribution.

INCLUDE terms like:
- Novel methods or frameworks introduced or used (e.g. MR-MAE, BEiT, DINO, CLIP)
- Specific architectural components (e.g. asymmetric encoder-decoder, ViT patch embeddings)
- Paper-specific concepts (e.g. feature mimicking, mimic loss, visible token supervision)
- Named training strategies or objectives (e.g. masked image modeling, contrastive pre-training)
- Key benchmarks or datasets referenced (e.g. ImageNet-1K, COCO)
- Specialized terms whose meaning or usage is particularly important in this paper

EXCLUDE generic terms that appear in most ML papers:
- loss, training, model, layer, batch, epoch, gradient, dataset, accuracy,
  inference, parameter, weight, output, input, feature, vector, matrix,
  function, network, performance, result, experiment

For every term you identify, assign a jargon_score from 1 to 10:
- 10 = coined, introduced, or substantially redefined in this specific paper
- 7-9 = well-known AI/ML jargon central to this paper's contribution
- 4-6 = technical term used as supporting context
- 1-3 = borderline paper-specific term

Limit output to top 12-15 most important terms.

Return ONLY a valid JSON object in this exact shape:
{
  "terms": [
    {
      "term": "<term as it appears in paper>",
      "jargon_score": <integer 1-10>
    }
  ]
}

No extra keys, no explanation outside the JSON object.
"""


def get_paper_summary_for_extraction(sections: List[Dict[str, Any]], max_chars: int = 5500) -> str:
    """Extracts high-signal sections keeping total input under max_chars for token efficiency."""
    parts = []
    for sec in sections:
        title = sec.get("title", "")
        title_lower = title.lower()
        if any(skip in title_lower for skip in ["reference", "bibliography", "acknowledg"]):
            continue

        content = sec.get("content", "").strip()
        is_priority = any(
            k in title_lower
            for k in ["preamble", "abstract", "intro", "overview", "method", "approach", "architecture"]
        )

        if is_priority and content:
            parts.append(f"[{title}]\n{content[:1200]}")
        elif title:
            excerpt = content[:250] if content else ""
            parts.append(f"[{title}]\n{excerpt}")

        for sub in sec.get("subsections", []):
            sub_title = sub.get("title", "")
            sub_content = sub.get("content", "").strip()
            if sub_title:
                parts.append(f"  Subsection: {sub_title} - {sub_content[:150]}")

    full_summary = "\n\n".join(parts)
    if len(full_summary) > max_chars:
        full_summary = full_summary[:max_chars]
    return full_summary


def find_occurrences_in_sections(term: str, sections: List[Dict[str, Any]], max_occurrences: int = 3) -> List[str]:
    """Finds exact sentences in paper sections where the given term appears."""
    occurrences = []
    if not term or len(term.strip()) < 2:
        return occurrences

    term_pattern = re.compile(rf'\b{re.escape(term)}\b', re.IGNORECASE)

    def extract_from_text(text: str):
        sentences = re.split(r'(?<=[.!?])\s+', text)
        for sent in sentences:
            sent_clean = sent.strip().replace('\n', ' ')
            if len(sent_clean) > 15 and term_pattern.search(sent_clean):
                if sent_clean not in occurrences:
                    occurrences.append(sent_clean)
                if len(occurrences) >= max_occurrences:
                    return

    def traverse(sec_list):
        for sec in sec_list:
            if len(occurrences) >= max_occurrences:
                break
            content = sec.get("content", "")
            if content:
                extract_from_text(content)
            subsections = sec.get("subsections", [])
            if subsections:
                traverse(subsections)

    traverse(sections)
    return occurrences


class TermExtractorAgent:
    """Agent 1: extracts AI/ML-specific terms from parsed paper JSON."""

    def __init__(self, model: str = GROQ_PRIMARY_MODEL):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GROQ_API_KEY is not set. Add it to your .env file."
            )
        self.client = Groq(api_key=api_key)
        self.model = model

    def _call_llm_with_retry(
        self,
        messages: List[Dict[str, str]],
        max_retries: int = 4,
    ) -> str:
        """Helper to call Groq with exponential backoff and automatic model fallback."""
        current_model = self.model
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=current_model,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=1024,
                    response_format={"type": "json_object"},
                )
                return response.choices[0].message.content
            except Exception as e:
                err_str = str(e).lower()
                is_rate_limit_or_json_error = any(
                    k in err_str
                    for k in [
                        "429",
                        "rate limit",
                        "tpm",
                        "rpm",
                        "tpd",
                        "tokens per day",
                        "rate_limit_exceeded",
                        "json_validate_failed",
                    ]
                )
                if is_rate_limit_or_json_error:
                    if current_model != GROQ_FALLBACK_MODEL:
                        print(
                            f"[TermExtractorAgent] Groq notice ({err_str[:60]}...) on '{current_model}'. Switching to fallback model '{GROQ_FALLBACK_MODEL}'..."
                        )
                        current_model = GROQ_FALLBACK_MODEL
                        self.model = GROQ_FALLBACK_MODEL
                        time.sleep(1.0)
                        continue
                    else:
                        wait_time = (attempt + 1) * 3.0
                        print(
                            f"[TermExtractorAgent] Waiting {wait_time}s on fallback model (attempt {attempt + 1}/{max_retries})..."
                        )
                        time.sleep(wait_time)
                else:
                    raise e
        raise RuntimeError("TermExtractorAgent exceeded maximum retry attempts")

    def run(self, paper_sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extracts domain-specific terms from the paper and attaches matched occurrences.

        Args:
            paper_sections: Structured section list from parse_pdf_to_json().

        Returns:
            List of dicts: [{"term": str, "jargon_score": int, "occurrences": [str, ...]}, ...]
        """
        paper_summary = get_paper_summary_for_extraction(paper_sections)

        user_message = (
            "Here is the research paper summary. "
            "Extract the top domain-specific AI/ML terms.\n\n"
            f"{paper_summary}"
        )

        raw = self._call_llm_with_retry([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ])

        parsed = json.loads(raw)
        extracted_list = []
        if isinstance(parsed, list):
            extracted_list = parsed
        elif isinstance(parsed, dict):
            if "terms" in parsed and isinstance(parsed["terms"], list):
                extracted_list = parsed["terms"]
            else:
                for v in parsed.values():
                    if isinstance(v, list):
                        extracted_list = v
                        break

        # Post-process: attach occurrences via fast Python regex search
        final_terms = []
        for item in extracted_list:
            if not isinstance(item, dict):
                continue
            term_str = item.get("term", "").strip()
            if not term_str:
                continue

            jargon_score = item.get("jargon_score", 5)
            occurrences = find_occurrences_in_sections(term_str, paper_sections)

            final_terms.append({
                "term": term_str,
                "jargon_score": jargon_score,
                "occurrences": occurrences,
            })

        return final_terms
