"""Pydantic schemas.

Two groups of models on purpose:
  - LLMExtraction / Decision / Action: the shape we force the LLM's output into.
    This is the contract between "semantic understanding" (LLM) and
    "deterministic logic" (Python rules in rules.py).
  - Issue / AnalyseRequest / AnalyseResponse: the API contract exposed to n8n.
"""
from typing import List, Optional

from pydantic import BaseModel, Field


class Decision(BaseModel):
    decision: str
    affected_disciplines: List[str] = Field(default_factory=list)


class Action(BaseModel):
    action: str
    owner: Optional[str] = None
    deadline: Optional[str] = None  # ISO date "YYYY-MM-DD", or null if not stated
    affected_deliverable: Optional[str] = None
    dependencies: List[str] = Field(default_factory=list)


class LLMExtraction(BaseModel):
    """Exactly what the LLM is allowed to produce. Nothing else."""

    decisions: List[Decision] = Field(default_factory=list)
    actions: List[Action] = Field(default_factory=list)


class Issue(BaseModel):
    type: str
    severity: str  # "low" | "medium" | "high"
    message: str


class AnalyseRequest(BaseModel):
    project_id: str
    text: str


class AnalyseResponse(BaseModel):
    project_id: str
    decisions: List[Decision]
    actions: List[Action]
    issues: List[Issue]
    requires_attention: bool


class Deliverable(BaseModel):
    deliverable_id: str
    name: str
    discipline: str
    owner: Optional[str] = None
    planned_date: Optional[str] = None
    status: str
