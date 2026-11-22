from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    database_path: Path
    admin_password: str
    deepseek_api_key: str
    hf_token: str
    default_provider: str
    default_model: str
    app_env: str

    @property
    def deepseek_configured(self) -> bool:
        return bool(self.deepseek_api_key.strip())

    @property
    def admin_configured(self) -> bool:
        return bool(self.admin_password.strip())

    @property
    def huggingface_configured(self) -> bool:
        return bool(self.hf_token.strip())


def load_settings() -> Settings:
    raw_db_path = os.getenv("APP_DATABASE_PATH", "data/fintwin.db")
    db_path = Path(raw_db_path)
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return Settings(
        database_path=db_path,
        admin_password=os.getenv("ADMIN_PASSWORD", ""),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        hf_token=os.getenv("HF_TOKEN", ""),
        default_provider=os.getenv("DEFAULT_LLM_PROVIDER", "huggingface"),
        default_model=os.getenv("DEFAULT_LLM_MODEL", "Qwen/Qwen3.5-9B"),
        app_env=os.getenv("APP_ENV", "development"),
    )

