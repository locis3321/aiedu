"""账号域请求模型（Pydantic v2）。"""

from pydantic import BaseModel, Field


class SmsSendRequest(BaseModel):
    phone: str = Field(min_length=5, max_length=20)


class SmsLoginRequest(BaseModel):
    phone: str = Field(min_length=5, max_length=20)
    code: str = Field(min_length=4, max_length=8)


class WechatLoginRequest(BaseModel):
    code: str = Field(min_length=1)


class ConsentGrantRequest(BaseModel):
    consent_key: str = Field(min_length=1, max_length=48)


class ChildCreateRequest(BaseModel):
    nickname: str = Field(min_length=1, max_length=32)
    grade: str | None = Field(default=None, max_length=16)
    age_group: str | None = Field(default=None, max_length=16)
    textbook_version: str | None = Field(default=None, max_length=32)


class ChildUpdateRequest(BaseModel):
    nickname: str | None = Field(default=None, min_length=1, max_length=32)
    grade: str | None = Field(default=None, max_length=16)
    age_group: str | None = Field(default=None, max_length=16)
    textbook_version: str | None = Field(default=None, max_length=32)


class UsageSettingsRequest(BaseModel):
    daily_minutes: int | None = Field(default=None, ge=0, le=24 * 60)
    continuous_minutes: int | None = Field(default=None, ge=0, le=24 * 60)
    rest_minutes: int | None = Field(default=None, ge=0, le=24 * 60)
    companion_enabled: bool | None = None


class ParentProfileUpdateRequest(BaseModel):
    nickname: str | None = Field(default=None, min_length=1, max_length=64)
