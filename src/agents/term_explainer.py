"""term_explainer.py

Agent 2 — AI/ML Term Explainer.

Receives the list of extracted terms (from Agent 1) plus the original parsed
paper JSON. For each term it produces:
  (a) context_definition  — what the term means WITHIN this specific paper
  (b) general_definition  — what the term means broadly in the AI/ML field

Uses Groq LLM with the paper's own sentences as grounding context.
"""

import json
import os
from typing import Any, Dict, List

from groq import Groq
from dotenv import load_dotenv

load_dotenv()

GROQ_MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """\
You are an expert ML educator explaining technical AI/ML concepts to a graduate
student audience. For each term you receive:

1. context_definition: Explain what this term means SPECIFICALLY within this
   paper. Use the paper's own wording and sentences to ground your explanation.
   Be precise about how the authors use or extend this concept.

2. general_definition: Explain what this term means BROADLY in the AI/ML field,
   independent of this specific paper. Write a clear, accessible definition.

Return ONLY a valid JSON object in this exact shape:
{
  "term": "<term>",
  "context_definition": "<explanation within the paper>",
  "general_definition": "<broad field definition>"
}

No extra keys, no explanation outside the JSON.
"""


class TermExplainerAgent:
    """Agent 2: produces in-context and general definitions for extracted terms."""

    def __init__(self, model: str = GROQ_MODEL):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GROQ_API_KEY is not set. Add it to your .env file."
            )
        self.client = Groq(api_key=api_key)
        self.model = model

    def _explain_term(
        self,
        term: str,
        occurrences: List[str],
        paper_title: str,
    ) -> Dict[str, Any]:
        """Calls LLM to explain a single term."""
        occurrence_block = "\n".join(
            f"- {s}" for s in occurrences[:5]  # cap to 5 sentences to keep prompt lean
        )
        user_message = (
            f"Paper title: {paper_title}\n\n"
            f"Term: {term}\n\n"
            f"Sentences from the paper where this term appears:\n{occurrence_block}\n\n"
            "Now produce the two definitions."
        )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content
        return json.loads(raw)

    def run(
        self,
        extracted_terms: List[Dict[str, Any]],
        paper_sections: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Explains every extracted term.

        Args:
            extracted_terms: Output from TermExtractorAgent.run().
            paper_sections: Original parsed paper JSON (for paper title).

        Returns:
            List of dicts: [{term, jargon_score, context_definition, general_definition, occurrences}, ...]
        """
        # Extract paper title from the Preamble section
        paper_title = "the paper"
        for sec in paper_sections:
            if sec.get("title") == "Preamble" and sec.get("content"):
                paper_title = sec["content"]
                break

        results = []
        for item in extracted_terms:
            term = item.get("term", "")
            occurrences = item.get("occurrences", [])
            if not term:
                continue

            explained = self._explain_term(term, occurrences, paper_title)

            # Carry over fields from Agent 1 output
            explained["jargon_score"] = item.get("jargon_score")
            explained["occurrences"] = occurrences
            results.append(explained)

        return results
