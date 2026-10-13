import json
import logging
import os
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from openai import OpenAI, APIStatusError, APITimeoutError
from pydantic import ValidationError
from dotenv import load_dotenv

from src.llm.schema import TriageOutput, TriageCategory, TriageUrgency

load_dotenv()

PROMPT_PATH = Path("prompts/triage-v1.md")
LOGS_DIR = Path("logs")

# Structured cost logger
logging.basicConfig(level=logging.INFO)
cost_logger = logging.getLogger("llm_cost")


def get_client() -> OpenAI:
    """Client configured with explicit 30s timeout and max_retries=0 to avoid silent double retries."""
    return OpenAI(
        base_url=os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1/"),
        api_key=os.environ.get("LLM_API_KEY", "ollama"),
        timeout=30.0,
        max_retries=0  # Disables SDK implicit retries; our custom retry policy handles backoff explicitly
    )


def _log_call_cost(prompt_version: str, model: str, in_tokens: int, out_tokens: int, duration_ms: float, needed_repair: bool):
    """Write structured cost log line per call."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "prompt_version": prompt_version,
        "model": model,
        "input_tokens": in_tokens,
        "output_tokens": out_tokens,
        "duration_ms": round(duration_ms, 2),
        "needed_repair": needed_repair
    }
    with open(LOGS_DIR / "cost.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    cost_logger.info(f"LLM COST: {entry}")


def _execute_with_retry_policy(client: OpenAI, model: str, messages: list[dict], max_attempts: int = 3):
    """Explicit retry policy:

    - Retries on APITimeoutError, 429 RateLimit, and 5xx Server errors with exponential backoff + jitter.
    - NEVER retries on 400, 401, or 403 (fails immediately without burning quota).
    """
    attempt = 0
    while attempt < max_attempts:
        attempt += 1
        try:
            return client.chat.completions.create(
                model=model,
                temperature=0.1,
                messages=messages
            )
        except APITimeoutError as te:
            if attempt >= max_attempts:
                raise TimeoutError(f"Model call timed out after 30s: {te}")
            backoff = (2 ** (attempt - 1)) + random.uniform(0.1, 0.5)
            time.sleep(backoff)
        except APIStatusError as e:
            # 400, 401, 403 -> Never retry
            if e.status_code in (400, 401, 403):
                raise
            # 429 or 5xx -> Retry with backoff
            if e.status_code == 429 or e.status_code >= 500:
                if attempt >= max_attempts:
                    raise
                # Check for Retry-After header if present
                retry_after = getattr(e.response, "headers", {}).get("retry-after") if hasattr(e, "response") else None
                if retry_after and retry_after.isdigit():
                    time.sleep(float(retry_after))
                else:
                    backoff = (2 ** (attempt - 1)) + random.uniform(0.1, 0.5)
                    time.sleep(backoff)
            else:
                raise


def _strip_markdown_fence(text: str) -> str:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()
    return text


def _quarantine_failure(input_text: str, raw_output: str, error_message: str):
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "prompt_version": "triage-v1",
        "input": input_text,
        "raw_output": raw_output,
        "error": error_message
    }
    with open(LOGS_DIR / "quarantine.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def triage_production(user_text: str) -> TriageOutput:
    """Production triage handler with kill-switch, timeout, retries, parse-repair, and cost logging."""
    # 1. Kill-switch check
    if os.environ.get("LLM_ENABLED", "true").lower() in ("false", "0", "no"):
        # Safe deterministic fallback when model is disabled
        return TriageOutput(
            category=TriageCategory.other,
            urgency=TriageUrgency.normal,
            confidence=0.5,
            reason="Kill switch active: LLM is disabled via LLM_ENABLED=false."
        )

    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    client = get_client()
    model_name = os.environ.get("LLM_MODEL", "gemma2:2b")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text}
    ]

    t0 = time.time()
    resp1 = _execute_with_retry_policy(client, model_name, messages)
    raw_output1 = resp1.choices[0].message.content or ""
    needed_repair = False

    try:
        clean = _strip_markdown_fence(raw_output1)
        result = TriageOutput.model_validate_json(clean)
    except (json.JSONDecodeError, ValidationError, Exception) as err1:
        # Repair attempt
        needed_repair = True
        repair_msg = (
            f"Your previous answer was rejected for this reason: {err1}.\n"
            f"Your previous raw output was:\n{raw_output1}\n"
            "Return ONLY corrected JSON matching the schema with no extra text."
        )
        messages.append({"role": "assistant", "content": raw_output1})
        messages.append({"role": "user", "content": repair_msg})

        resp2 = _execute_with_retry_policy(client, model_name, messages)
        raw_output2 = resp2.choices[0].message.content or ""

        try:
            clean2 = _strip_markdown_fence(raw_output2)
            result = TriageOutput.model_validate_json(clean2)
            resp1 = resp2  # use tokens from final response
        except Exception as err2:
            _quarantine_failure(user_text, raw_output2, str(err2))
            raise RuntimeError(f"Model failed schema validation after repair attempt: {err2}")

    duration_ms = (time.time() - t0) * 1000
    in_tokens = getattr(resp1.usage, "prompt_tokens", len(user_text) // 4) if hasattr(resp1, "usage") and resp1.usage else 0
    out_tokens = getattr(resp1.usage, "completion_tokens", len(raw_output1) // 4) if hasattr(resp1, "usage") and resp1.usage else 0

    _log_call_cost("triage-v1", model_name, in_tokens, out_tokens, duration_ms, needed_repair)
    return result
