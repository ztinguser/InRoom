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

    # 讨厌的校验
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
