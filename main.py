import os
from fastapi import FastAPI, HTTPException, status
from dotenv import load_dotenv

from src.llm.schema import TriageInput, TriageOutput, TriageCategory, TriageUrgency
from src.llm.service import triage_with_repair

load_dotenv()

app = FastAPI(
    title="FlyRank Triage API",
    description="Intelligent support message classification with structured LLM output",
    version="1.0.0"
)


@app.get("/")
def read_root():
    return {"name": "Triage API", "status": "running"}


@app.post("/triage", response_model=TriageOutput, status_code=status.HTTP_200_OK)
def triage_message(payload: TriageInput):
    """Classify incoming support messages into structured team actions."""
    # Stub mode check
    if os.environ.get("LLM_STUB", "0") == "1":
        return TriageOutput(
            category=TriageCategory.bug,
            urgency=TriageUrgency.normal,
            confidence=0.95,
            reason="Hardcoded stub response for Stage 1 validation."
        )

    try:
        return triage_with_repair(payload.text)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "LLM output failed validation after repair", "details": str(e)}
        )
