from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    deepseek_api_key: SecretStr = SecretStr("")
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_url: str = ""

    dashscope_api_key: SecretStr = SecretStr("")
    qwen_tts_model: str = "qwen3-tts-vd-realtime-2026-01-15"
    qwen_tts_voice: str = ""

    asr_model: str = "fun-asr-realtime-2026-02-28"

    database_url: str = "postgresql+psycopg://inroom:inroom@127.0.0.1:5432/inroom"

    app_origin: str = "http://127.0.0.1:8000"
    session_secret: SecretStr = SecretStr("")
    login_max_age: int = 8 * 60 * 60

    oidc_issuer: str = "http://127.0.0.1:8080/realms/inroom"
    oidc_client_id: str = "inroom-backend"
    oidc_client_secret: SecretStr = SecretStr("")
    # 不提供开发身份绕过；显式拒绝误配，避免部署者以为开关生效。
    dev_identity_enabled: bool = False

    # 讨厌的llm校验
    def validate_production(self) -> None:
        if self.app_env != "production":
            return

        required = {
            "DEEPSEEK_API_KEY": self.deepseek_api_key.get_secret_value(),
            "DEEPSEEK_URL": self.deepseek_url,
            "DASHSCOPE_API_KEY": self.dashscope_api_key.get_secret_value(),
            "QWEN_TTS_VOICE": self.qwen_tts_voice,
        }
        missing = [name for name, value in required.items() if not value.strip()]

        if missing:
            raise RuntimeError(f"生产配置缺失：{', '.join(missing)}")

    # 讨厌的identity校验
    def validate_identity(self) -> None:
        if self.dev_identity_enabled:
            raise RuntimeError("不支持开发身份绕过，请使用 OIDC 登录")
        if not self.session_secret.get_secret_value():
            raise RuntimeError("缺少 SESSION_SECRET")

        if self.app_env == "production":
            if not self.app_origin.startswith("https://"):
                raise RuntimeError("生产环境 APP_ORIGIN 必须使用 HTTPS")

            if not self.oidc_issuer.startswith("https://"):
                raise RuntimeError("生产环境 OIDC_ISSUER 必须使用 HTTPS")

            if not self.oidc_client_secret.get_secret_value():
                raise RuntimeError("缺少 OIDC_CLIENT_SECRET")
