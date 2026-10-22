"""应用配置：全部从环境变量（或 .env）读取，不硬编码任何凭据。"""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_DEFAULT_SECRET = "dev-only-insecure-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # 运行环境：development|production。production 下强制安全校验：
    # 默认 SECRET_KEY 拒绝启动；短信无凭据显式 503 不 dev 兜底。
    app_env: str = "development"

    # PostgreSQL（compose 服务 postgres）
    database_url: str = "postgresql+psycopg://aiedu:aiedu@127.0.0.1:5432/aiedu"

    # Redis / Celery broker（compose 映射到宿主 6380，避免与其他项目冲突）
    redis_url: str = "redis://127.0.0.1:6380/0"

    # 对象存储：开发默认本地磁盘适配器；s3 时走 S3 兼容协议（MinIO/AWS S3 等）
    storage_backend: str = "local"
    storage_local_dir: str = "./data/artifacts"
    s3_endpoint_url: str | None = None
    s3_bucket: str = "aiedu-artifacts"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None

    # --- 账号域（T2）---
    # JWT 签名密钥：仅开发默认值，生产必须通过环境变量覆盖（SECURITY_SECRET_KEY）
    security_secret_key: str = INSECURE_DEFAULT_SECRET
    # 凭据加密密钥（Fernet 派生材料）：默认与 JWT 密钥同源；生产建议显式拆分，
    # 避免 JWT 密钥轮换连带全部第三方凭据不可解密（重配/轮换依赖该值稳定性）。
    credential_encryption_key: str | None = None
    access_token_expire_minutes: int = 60 * 24 * 7
    child_token_expire_minutes: int = 60 * 12

    # 短信验证码（dev fallback 与防刷策略，规格 v2 §6）
    sms_dev_fixed_code: str = "123456"
    sms_code_ttl_seconds: int = 300
    sms_code_max_attempts: int = 5
    sms_send_cooldown_seconds: int = 60
    sms_max_per_day_per_phone: int = 10

    # 腾讯云短信（ak/sk 未配置 → dev fallback；签名/模板未配置 → 显式"未接入"）
    sms_secret_id: str | None = None
    sms_secret_key: str | None = None
    sms_sdk_app_id: str | None = None
    sms_sign_name: str | None = None
    sms_template_id: str | None = None

    # 微信小程序登录（未配置 → 显式"未接入"，不用模拟账号兜底）
    wechat_app_id: str | None = None
    wechat_app_secret: str | None = None

    # 运营后台开发态登录：无凭据签发管理 token，仅限本地开发；
    # 生产必须设为 false（接 SSO），否则任何人可获取管理权限（P1）
    admin_dev_login_enabled: bool = False
    # 题庄在线题库（第三方题源，匿名试用；2026-10-10 接入）
    question_service_url: str = "https://tizhuang.qcscience.cc/api"

    # TTS：MiMo-V2.5-TTS（小米平台，OpenAI 兼容，官方免费期）；
    # key 走环境变量不入库；供应商由管理端 tts_configs.provider 决定
    mimo_api_key: str | None = None
    mimo_base_url: str = "https://api.xiaomimimo.com/v1"
    mimo_tts_model: str = "mimo-v2.5-tts"

    # Grafana 基址（Trace 跳转；Tempo 数据源）
    grafana_base_url: str = "http://localhost:3000"

    # LLM（OpenAI 兼容接口；由环境注入，缺失时相关能力显式不可用）
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model_name: str | None = None
    embed_base_url: str | None = None
    embed_api_key: str | None = None
    embed_model_name: str | None = None

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_base_url and self.llm_api_key and self.llm_model_name)

    @model_validator(mode="after")
    def _production_safety(self) -> "Settings":
        """生产硬校验：默认密钥直接拒绝启动（否则任何人可伪造 JWT/凭据）。"""
        if self.app_env == "production" and self.security_secret_key == INSECURE_DEFAULT_SECRET:
            raise ValueError(
                "APP_ENV=production 时 SECURITY_SECRET_KEY 必须是安全随机值（拒绝默认密钥启动）"
            )
        return self

    @property
    def llm_base_url_normalized(self) -> str | None:
        """规范化 OpenAI 兼容 base_url：确保带 /v1 路径。

        内网兼容服务（如 one-api/new-api/vLLM）通常暴露 /v1/chat/completions；
        若只配置了服务根地址（如 http://host:port），请求会打到 Web UI 并返回
        HTML，SDK 解析成 str 导致 'str' object has no attribute 'choices'。
        """
        if not self.llm_base_url:
            return None
        url = self.llm_base_url.rstrip("/")
        if url.endswith("/v1"):
            return url
        return f"{url}/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
