from enum import Enum
from pydantic import BaseModel, Field


class TriageCategory(str, Enum):
    billing = "billing"
    bug = "bug"
    feature = "feature"
    other = "other"


class TriageUrgency(str, Enum):
    low = "low"
    normal = "normal"
    high = "high"


class TriageInput(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000, description="Customer support message")


class TriageOutput(BaseModel):
    category: TriageCategory
    urgency: TriageUrgency
    confidence: float = Field(..., ge=0.0, le=1.0)
    reason: str = Field(..., min_length=1, max_length=500)
