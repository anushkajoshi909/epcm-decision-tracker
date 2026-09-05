"""LLM call for structured extraction only.

Design rule for this whole project: the LLM is used ONLY where semantic
understanding of free text is required (what was decided, who owns what,
which discipline is affected). Anything that is a deterministic check
(missing owner, missing deadline, deadline in the past, ...) lives in
rules.py as plain Python. See README.md "Why the LLM is only used for
semantic tasks" for the full rationale.
"""
import json
import os
from datetime import date
from pathlib import Path

from openai import OpenAI
from pydantic import ValidationError

from .models import LLMExtraction

_client: OpenAI | None = None


def _read_scadsai_key() -> str:
    return (Path.home() / ".scadsai-api-key").read_text().splitlines()[0].strip()


def get_client() -> OpenAI:
    """Lazy singleton so importing this module doesn't require env vars to
    already be set (useful for tests that don't touch the LLM).

    Defaults to the SCADS.AI endpoint, reading the key from
    ~/.scadsai-api-key. Set LLM_BASE_URL / LLM_API_KEY to point at a
    different OpenAI-compatible endpoint instead.
    """
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=os.getenv("LLM_BASE_URL", "https://llm.scads.ai/v1"),
            api_key=os.getenv("LLM_API_KEY") or _read_scadsai_key(),
        )
    return _client


MODEL = os.getenv("LLM_MODEL", "meta-llama/Llama-3.3-70B-Instruct")

SYSTEM_PROMPT_TEMPLATE = """You are an assistant that reads EPCM (Engineering, \
Procurement, Construction Management) meeting protocols and extracts \
structured information. You do not manage the project, you only extract \
what is explicitly stated.

Extract:
- decisions: each notable technical or project decision made during the \
meeting, and which disciplines it affects (e.g. "HVAC", "Electrical", \
"Structural", "Plumbing", "Fire Safety").
- actions: each concrete follow-up action, with:
  - owner: the person responsible, exactly as named in the text, or null if \
no one is named.
  - deadline: an ISO date "YYYY-MM-DD", or null if no deadline is stated. \
If only a day and month are given, assume the year {year}.
  - affected_deliverable: a deliverable/package code if one is mentioned \
(e.g. "EL-04"), else null.
  - dependencies: short phrases describing anything this action is blocked \
on or depends on. Empty list if none.

Rules:
- Do not invent information that is not present in the text.
- Do not resolve or guess an owner/deadline that is not explicitly stated.
- Respond with ONLY a single JSON object matching this JSON Schema, no \
markdown, no commentary:

{schema}
"""


class LLMExtractionError(Exception):
    pass


def _build_system_prompt() -> str:
    schema = json.dumps(LLMExtraction.model_json_schema(), indent=2)
    return SYSTEM_PROMPT_TEMPLATE.format(year=date.today().year, schema=schema)


def extract_structured(text: str, max_attempts: int = 2) -> LLMExtraction:
    """Call the LLM and validate its output against LLMExtraction.

    Controlled retry: if the model returns invalid JSON or JSON that fails
    Pydantic validation, we send the error back once and ask it to correct
    itself. No open-ended retry loop.
    """
    messages = [
        {"role": "system", "content": _build_system_prompt()},
        {"role": "user", "content": text},
    ]

    last_error: Exception | None = None
    for _ in range(max_attempts):
        try:
            response = get_client().chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=0,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content
            data = json.loads(raw)
            return LLMExtraction.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = exc
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Your previous response was not valid: {exc}. "
                        "Respond again with ONLY a valid JSON object matching "
                        "the schema."
                    ),
                }
            )
        except Exception as exc:  # LLM API/network failure - do not retry blindly
            raise LLMExtractionError(f"LLM API call failed: {exc}") from exc

    raise LLMExtractionError(
        f"LLM did not return a valid structured response after {max_attempts} "
        f"attempts: {last_error}"
    )
