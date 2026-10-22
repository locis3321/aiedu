"""积分域请求模型。"""

from pydantic import BaseModel, Field


class GrantRewardRequest(BaseModel):
    evidence_id: str = Field(min_length=1, max_length=32)


class RedeemRequest(BaseModel):
    item_id: str | None = Field(default=None, max_length=64)
