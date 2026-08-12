"""term_extractor.py

Agent 1 — AI/ML Term Extractor.

Receives the flattened text of a parsed research paper and uses Groq LLM
to extract domain-specific AI/ML terms that are significant to THIS paper's
specific contribution. Generic ML vocabulary (loss, training, model, layer)
is excluded unless the paper introduces a novel variant.
"""

import json
import os
from typing import Any, Dict, List

from groq import Groq
from dotenv import load_dotenv

load_dotenv()

GROQ_MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """\
You are an expert AI/ML researcher and technical writer. Your job is to read a
research paper and extract domain-specific terminology that is significant to
THIS paper's specific contribution — not generic ML vocabulary.

INCLUDE terms like:
- Novel methods or frameworks introduced or used (e.g. MR-MAE, BEiT, DINO, CLIP)
- Specific architectural components (e.g. asymmetric encoder-decoder, ViT patch embeddings)
- Paper-specific concepts (e.g. feature mimicking, mimic loss, visible token supervision)
- Named training strategies or objectives (e.g. masked image modeling, contrastive pre-training)
- Key benchmarks or datasets referenced (e.g. ImageNet-1K, COCO)

EXCLUDE generic terms that appear in every ML paper:
- loss, training, model, layer, batch, epoch, gradient, dataset, accuracy,
  inference, parameter, weight, output, input, feature, vector, matrix,
  function, network, performance, result, experiment

For every term you identify, also assign a jargon_score from 1 to 10:
- 10 = coined or redefined in this specific paper (e.g. "MR-MAE", "mimic loss")
- 7-9 = well-known AI/ML jargon that is central to this paper's contribution
         (e.g. "Masked Autoencoders", "contrastive learning", "Vision Transformer")
- 4-6 = technical term used as supporting context, not the paper's core novelty
         (e.g. "ImageNet-1K", "fine-tuning", "COCO")
- 1-3 = borderline — could appear in general tech writing, barely paper-specific
         (e.g. "representation", "pre-training", "downstream task")

Return ONLY a valid JSON array. Each element must be an object with:
{
  "term": "<the term as it appears in the paper>",
  "jargon_score": <integer 1-10>,
  "occurrences": ["<sentence 1 where term appears>", "<sentence 2 ...>"]
}

Do not include any explanation outside the JSON array.
"""


def flatten_sections(sections: List[Dict[str, Any]], depth: int = 0) -> str:
    """Recursively flattens the nested section JSON into plain text."""
    parts = []
    for sec in sections:
        title = sec.get("title", "")
        content = sec.get("content", "").strip()
        if content:
            parts.append(f"[{title}]\n{content}")
        subsections = sec.get("subsections", [])
        if subsections:
            parts.append(flatten_sections(subsections, depth + 1))
    return "\n\n".join(parts)


class TermExtractorAgent:
    """Agent 1: extracts AI/ML-specific terms from parsed paper JSON."""

    def __init__(self, model: str = GROQ_MODEL):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GROQ_API_KEY is not set. Add it to your .env file."
            )
        self.client = Groq(api_key=api_key)
        self.model = model

    def run(self, paper_sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extracts domain-specific terms from the paper.

        Args:
            paper_sections: Structured section list from parse_pdf_to_json().

        Returns:
            List of dicts: [{"term": str, "occurrences": [str, ...]}, ...]
        """
        flat_text = flatten_sections(paper_sections)

        user_message = (
            "Here is the full text of the research paper. "
            "Extract all domain-specific AI/ML terms.\n\n"
            f"{flat_text}"
        )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content
        parsed = json.loads(raw)

        # The model may return {"terms": [...]} or just [...]
        if isinstance(parsed, list):
            return parsed
        # Unwrap whichever key holds the list
        for value in parsed.values():
            if isinstance(value, list):
                return value

        return []
