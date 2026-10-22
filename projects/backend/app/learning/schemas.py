"""学习域请求模型（Pydantic v2）。"""

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    source: str = Field(default="home", max_length=16)  # home|ask|paper


class StartActivityRequest(BaseModel):
    kind: str = Field(default="gate", max_length=16)  # gate|variant|transfer
    input: dict | None = None  # {kind:'problem'|'concept', content:...}
    lesson_id: str | None = Field(default=None, max_length=64)
    revision: int | None = None


class SubmitAttemptRequest(BaseModel):
    step_id: str = Field(min_length=1, max_length=64)
    value: str | int | float | None = None


class HintRequest(BaseModel):
    step_id: str = Field(min_length=1, max_length=64)


class CompleteActivityRequest(BaseModel):
    value: str | int | float | None = None
