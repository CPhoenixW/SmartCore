from __future__ import annotations

from datetime import datetime
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

ComputerAnalysisModel: TypeAlias = Literal[
    "qwen3.7-plus", "deepseek-v4-flash", "deepseek-v4-flash-0731"
]
SUPPORTED_COMPUTER_ANALYSIS_MODELS = {
    "qwen3.7-plus",
    "deepseek-v4-flash",
    "deepseek-v4-flash-0731",
}


class PlanAssessmentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evtId: str = Field(min_length=1, max_length=64)
    state: Literal["not_started", "partial", "substantially_executed", "unclear"]
    confidence: Literal["high", "medium", "low"]
    evidenceCodes: list[str] = Field(default_factory=list, max_length=10)
    note: str | None = Field(default=None, max_length=500)


class TopicBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=40)
    summary: str | None = Field(default=None, max_length=300)
    activeSeconds: int = Field(default=0, ge=0, le=86400)
    sessionIds: list[str] = Field(default_factory=list, max_length=30)
    contextIds: list[str] = Field(default_factory=list, max_length=30)


class HourlyAnalysisBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    deviceId: str = Field(min_length=1, max_length=32)
    hourStart: datetime
    status: Literal["complete", "failed"]
    title: str | None = Field(default=None, max_length=10)
    summary: str | None = Field(default=None, max_length=800)
    planAssessments: list[PlanAssessmentBody] = Field(default_factory=list, max_length=30)
    topics: list[TopicBody] = Field(default_factory=list, max_length=10)
    evidence: dict = Field(default_factory=dict)
    model: ComputerAnalysisModel | None = None
    promptVersion: Literal["computer-analysis-v1"] = "computer-analysis-v1"
    errorMessage: str | None = Field(default=None, max_length=1000)


class DailyLogBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    deviceId: str = Field(min_length=1, max_length=32)
    logDate: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    status: Literal["complete", "failed"]
    title: str | None = Field(default=None, max_length=10)
    summary: str | None = Field(default=None, max_length=1200)
    topics: list[TopicBody] = Field(default_factory=list, max_length=10)
    planAssessments: list[PlanAssessmentBody] = Field(default_factory=list, max_length=30)
    reminderSummary: list[dict] = Field(default_factory=list, max_length=50)
    hourlyAnalysisIds: list[str] = Field(default_factory=list, max_length=48)
    workBlockIds: list[str] = Field(default_factory=list, max_length=100)
    phase: Literal["preview", "final"] = "final"
    model: ComputerAnalysisModel | None = None
    promptVersion: Literal["computer-analysis-v1", "computer-work-block-v1"] = (
        "computer-work-block-v1"
    )
    errorMessage: str | None = Field(default=None, max_length=1000)


class PlanSemanticAssessmentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evtId: str = Field(min_length=1, max_length=64)
    semanticAlignment: Literal["aligned", "partially_aligned", "unrelated", "unclear"]
    confidence: Literal["high", "medium", "low"]
    evidenceCodes: list[str] = Field(default_factory=list, max_length=10)
    note: str | None = Field(default=None, max_length=500)


class WorkBlockAnalysisBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    runId: str = Field(min_length=1, max_length=32)
    status: Literal["complete", "failed"]
    action: Literal["start", "extend", "switch", "complete", "ignore"] | None = None
    topicKey: str | None = Field(default=None, max_length=100)
    title: str | None = Field(default=None, max_length=20)
    summary: str | None = Field(default=None, max_length=800)
    progress: str | None = Field(default=None, max_length=300)
    outcome: str | None = Field(default=None, max_length=300)
    blocker: str | None = Field(default=None, max_length=300)
    nextStep: str | None = Field(default=None, max_length=300)
    planSemanticAssessments: list[PlanSemanticAssessmentBody] = Field(
        default_factory=list, max_length=30
    )
    evidenceContextIds: list[str] = Field(default_factory=list, max_length=100)
    model: ComputerAnalysisModel | None = None
    promptVersion: Literal["computer-work-block-v1"] = "computer-work-block-v1"
    errorMessage: str | None = Field(default=None, max_length=1000)


class HourlyInference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=10)
    summary: str = Field(min_length=1, max_length=800)
    planAssessments: list[PlanAssessmentBody] = Field(default_factory=list, max_length=30)
    topics: list[TopicBody] = Field(default_factory=list, max_length=10)


class DailyInference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=10)
    summary: str = Field(min_length=1, max_length=1200)
    topics: list[TopicBody] = Field(default_factory=list, max_length=10)
    planAssessments: list[PlanAssessmentBody] = Field(default_factory=list, max_length=30)


class WorkBlockInference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topicKey: str | None = Field(default=None, max_length=100)
    title: str | None = Field(default=None, max_length=20)
    summary: str | None = Field(default=None, max_length=800)
    progress: str | None = Field(default=None, max_length=300)
    outcome: str | None = Field(default=None, max_length=300)
    blocker: str | None = Field(default=None, max_length=300)
    nextStep: str | None = Field(default=None, max_length=300)
    planSemanticAssessments: list[PlanSemanticAssessmentBody] = Field(
        default_factory=list, max_length=30
    )
    evidenceContextIds: list[str] = Field(default_factory=list, max_length=100)
