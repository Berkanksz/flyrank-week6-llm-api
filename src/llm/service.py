import json
import os
import re
from pathlib import Path
from pydantic import ValidationError
from dotenv import load_dotenv

from src.llm.client import get_client, PROMPT_PATH
from src.llm.schema import TriageOutput

load_dotenv()

LOGS_DIR = Path("logs")


def _strip_markdown_fence(text: str) -> str:
    """Strip markdown ```json code fences and trim whitespace."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()
    return text


def _quarantine_failure(input_text: str, raw_output: str, error_message: str):
    """Log unrepairable model failures to logs/quarantine.jsonl."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "prompt_version": "triage-v1",
        "input": input_text,
        "raw_output": raw_output,
        "error": error_message
    }
    with open(LOGS_DIR / "quarantine.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def parse_and_validate(raw_text: str) -> TriageOutput:
    clean = _strip_markdown_fence(raw_text)
    # Validate against Pydantic schema
    return TriageOutput.model_validate_json(clean)


def triage_with_repair(user_text: str, custom_prompt_path: Path = PROMPT_PATH) -> TriageOutput:
    """Call model, parse & validate schema, repair once if failed, quarantine if still bad."""
    system_prompt = custom_prompt_path.read_text(encoding="utf-8")
    client = get_client()
    model_name = os.environ.get("LLM_MODEL", "gemma2:2b")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text}
    ]

    # Attempt 1
    resp1 = client.chat.completions.create(
        model=model_name,
        temperature=0.1,
        messages=messages
    )
    raw_output1 = resp1.choices[0].message.content or ""

    try:
        return parse_and_validate(raw_output1)
    except (json.JSONDecodeError, ValidationError, Exception) as err1:
        # Attempt 2: Repair once
        repair_instruction = (
            f"Your previous answer was rejected for this reason: {err1}.\n"
            f"Your previous raw output was:\n{raw_output1}\n"
            "Return ONLY corrected JSON matching the schema with no extra text."
        )
        messages.append({"role": "assistant", "content": raw_output1})
        messages.append({"role": "user", "content": repair_instruction})

        resp2 = client.chat.completions.create(
            model=model_name,
            temperature=0.0,
            messages=messages
        )
        raw_output2 = resp2.choices[0].message.content or ""

        try:
            return parse_and_validate(raw_output2)
        except Exception as err2:
            # Both attempts failed -> quarantine failure and raise
            _quarantine_failure(user_text, raw_output2, str(err2))
            raise RuntimeError(f"Model failed schema validation after repair attempt: {err2}")
