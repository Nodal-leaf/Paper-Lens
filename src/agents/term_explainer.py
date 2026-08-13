"""term_explainer.py

Agent 2 — AI/ML Term Explainer.

Receives the list of extracted terms (from Agent 1) plus the original parsed
paper JSON. For each term it produces:
  (a) context_definition  — what the term means WITHIN this specific paper
  (b) general_definition  — what the term means broadly in the AI/ML field

Uses Groq LLM with the paper's own sentences as grounding context.
Includes batching (batch_size=3), max_tokens=4096 allocation, automatic model fallback,
and full monitoring logging for token usage, latency, inputs, outputs, and errors.
"""

import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from groq import Groq
from dotenv import load_dotenv
from src.monitoring.logger import monitor_logger

load_dotenv()

GROQ_PRIMARY_MODEL = "llama-3.1-8b-instant"
GROQ_FALLBACK_MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """\
You are an expert ML educator explaining technical AI/ML concepts to people who
end up opening many tabs on their browser while reading a research paper because
of unfamiliar terms. For each term you receive:

1. context_definition: Explain what this term means SPECIFICALLY within this
paper in detail. Use the paper's own terminology, wording, and relevant sentences
to ground your explanation. Be precise about how the authors use the term, its
role in the paper, and how it relates to their method, architecture, objective,
or contribution. If the authors use the term in a way that differs from its
standard meaning, explicitly explain that distinction. Do not invent or assume
paper-specific details that are not supported by the paper.

2. general_definition: Explain what this term means BROADLY in the AI/ML field,
independent of this specific paper. Give the standard technical meaning in a
clear, accessible, and concise way. Focus on the core intuition, purpose, and
how the concept is generally used in AI/ML.

The key distinction is:
- context_definition = What does this term mean HERE, in this paper?
- general_definition = What does this term normally mean in AI/ML?

Return ONLY a valid JSON object with a single key "explained_terms" containing a list of objects in this exact shape:
{
  "explained_terms": [
    {
      "term": "<term>",
      "context_definition": "<explanation within the paper>",
      "general_definition": "<broad field definition>"
    }
  ]
}

No extra keys, no explanation outside the JSON.
"""


class TermExplainerAgent:
    """Agent 2: produces in-context and general definitions for extracted terms."""

    def __init__(self, model: str = GROQ_PRIMARY_MODEL, batch_size: int = 3):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GROQ_API_KEY is not set. Add it to your .env file."
            )
        self.client = Groq(api_key=api_key)
        self.model = model
        self.batch_size = batch_size

    def _call_llm_with_retry(
        self,
        messages: List[Dict[str, str]],
        max_retries: int = 4,
    ) -> Tuple[str, Dict[str, int]]:
        """Helper to call Groq with exponential backoff, automatic fallback, and token metrics."""
        current_model = self.model
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=current_model,
                    messages=messages,
                    temperature=0.2,
                    max_tokens=4096,
                    response_format={"type": "json_object"},
                )
                usage = {
                    "prompt_tokens": getattr(response.usage, "prompt_tokens", 0) if response.usage else 0,
                    "completion_tokens": getattr(response.usage, "completion_tokens", 0) if response.usage else 0,
                    "total_tokens": getattr(response.usage, "total_tokens", 0) if response.usage else 0,
                }
                return response.choices[0].message.content, usage
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
                        "max completion tokens reached",
                    ]
                )
                if is_rate_limit_or_json_error:
                    if current_model != GROQ_FALLBACK_MODEL:
                        print(
                            f"[TermExplainerAgent] Groq notice ({err_str[:60]}...) on '{current_model}'. Switching to fallback model '{GROQ_FALLBACK_MODEL}'..."
                        )
                        current_model = GROQ_FALLBACK_MODEL
                        self.model = GROQ_FALLBACK_MODEL
                        time.sleep(1.0)
                        continue
                    else:
                        wait_time = (attempt + 1) * 3.0
                        print(
                            f"[TermExplainerAgent] Waiting {wait_time}s on fallback model (attempt {attempt + 1}/{max_retries})...."
                        )
                        time.sleep(wait_time)
                else:
                    raise e
        raise RuntimeError("TermExplainerAgent exceeded maximum retry attempts")

    def _explain_batch(
        self,
        terms_batch: List[Dict[str, Any]],
        paper_title: str,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        """Calls LLM to explain a batch of terms in a single request and returns output + token usage."""
        batch_prompt_parts = [f"Paper title: {paper_title}\n"]
        for idx, item in enumerate(terms_batch, start=1):
            t = item.get("term", "")
            occs = item.get("occurrences", [])
            occ_str = "\n".join(f"  - {s}" for s in occs[:3])
            batch_prompt_parts.append(f"Term {idx}: {t}\nOccurrences:\n{occ_str}\n")

        batch_prompt_parts.append(
            "Now produce the two definitions for each of the terms listed above."
        )
        user_message = "\n".join(batch_prompt_parts)

        raw, usage = self._call_llm_with_retry(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ]
        )

        parsed = json.loads(raw)
        results_list = []
        if isinstance(parsed, dict):
            if "explained_terms" in parsed and isinstance(
                parsed["explained_terms"], list
            ):
                results_list = parsed["explained_terms"]
            else:
                for v in parsed.values():
                    if isinstance(v, list):
                        results_list = v
                        break
        elif isinstance(parsed, list):
            results_list = parsed

        return results_list, usage

    def run(
        self,
        extracted_terms: List[Dict[str, Any]],
        paper_sections: List[Dict[str, Any]],
        request_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Explains every extracted term using batched requests to avoid Groq rate limits.

        Args:
            extracted_terms: Output from TermExtractorAgent.run().
            paper_sections: Original parsed paper JSON (for paper title).
            request_id: Optional correlation ID for monitoring traces.

        Returns:
            List of dicts: [{term, jargon_score, context_definition, general_definition, occurrences}, ...]
        """
        t0 = time.time()
        error_msg = None
        final_results = []
        accumulated_tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        try:
            paper_title = "the paper"
            for sec in paper_sections:
                if sec.get("title") == "Preamble" and sec.get("content"):
                    paper_title = sec["content"]
                    break

            terms_list = [item for item in extracted_terms if item.get("term")]
            results_map = {}

            total_batches = (len(terms_list) + self.batch_size - 1) // max(
                1, self.batch_size
            )
            for i in range(0, len(terms_list), self.batch_size):
                batch = terms_list[i : i + self.batch_size]
                current_batch_num = (i // self.batch_size) + 1
                print(
                    f"[TermExplainerAgent] Explaining batch {current_batch_num}/{total_batches} ({len(batch)} terms)..."
                )

                try:
                    explained_batch, usage = self._explain_batch(batch, paper_title)
                    accumulated_tokens["prompt_tokens"] += usage.get("prompt_tokens", 0)
                    accumulated_tokens["completion_tokens"] += usage.get("completion_tokens", 0)
                    accumulated_tokens["total_tokens"] += usage.get("total_tokens", 0)

                    for exp in explained_batch:
                        t_name = exp.get("term", "")
                        if t_name:
                            results_map[t_name.lower()] = exp
                except Exception as b_err:
                    print(f"[TermExplainerAgent] Error during batch processing: {b_err}")

                time.sleep(0.4)

            # Assemble final results list maintaining original order and metadata
            for item in terms_list:
                t = item.get("term", "")
                t_lower = t.lower()
                exp = results_map.get(t_lower, {})

                final_results.append(
                    {
                        "term": t,
                        "jargon_score": item.get("jargon_score", 5),
                        "context_definition": exp.get(
                            "context_definition",
                            "Paper-specific context definition unavailable.",
                        ),
                        "general_definition": exp.get(
                            "general_definition", "General definition unavailable."
                        ),
                        "occurrences": item.get("occurrences", []),
                    }
                )
        except Exception as err:
            error_msg = str(err)
            raise err
        finally:
            latency_ms = (time.time() - t0) * 1000.0
            monitor_logger.log(
                level="ERROR" if error_msg else "INFO",
                endpoint="TermExplainerAgent.run",
                agent_invoked="TermExplainerAgent",
                input_data={"terms_to_explain_count": len(extracted_terms)},
                output_data={"explained_terms_count": len(final_results)},
                latency_ms=latency_ms,
                tokens_used=accumulated_tokens,
                errors=error_msg,
                request_id=request_id,
            )

        return final_results
