import os
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

PROMPT_PATH = Path("prompts/triage-v1.md")


def get_client() -> OpenAI:
    return OpenAI(
        base_url=os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1/"),
        api_key=os.environ.get("LLM_API_KEY", "ollama")
    )


def call_triage_model(user_text: str) -> str:
    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    client = get_client()
    response = client.chat.completions.create(
        model=os.environ.get("LLM_MODEL", "gemma2:2b"),
        temperature=0.1,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text}
        ]
    )
    return response.choices[0].message.content or ""
