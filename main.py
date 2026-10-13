import os
from fastapi import FastAPI, HTTPException, status
from dotenv import load_dotenv

from src.llm.schema import TriageInput, TriageOutput, TriageCategory, TriageUrgency

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
    # Stage 1: Stub mode check
    if os.environ.get("LLM_STUB", "0") == "1":
        return TriageOutput(
            category=TriageCategory.bug,
            urgency=TriageUrgency.normal,
            confidence=0.95,
            reason="Hardcoded stub response for Stage 1 validation."
        )

    # Placeholder for Stage 2 real model call
    return TriageOutput(
        category=TriageCategory.other,
        urgency=TriageUrgency.low,
        confidence=0.5,
        reason="Default response pending model wiring."
    )
