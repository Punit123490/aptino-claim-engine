from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore')
    google_api_key: SecretStr = SecretStr('')
    gemini_model: str = 'gemini-3.1-flash-lite'
    model_timeout_seconds: int = 90
    model_max_retries: int = 2
    model_min_interval_seconds: float = 13.0
    app_api_token: SecretStr = SecretStr('')
    app_port: int = 7860
    embedding_model: str = 'BAAI/bge-small-en-v1.5'
    reranker_model: str = 'ms-marco-TinyBERT-L-2-v2'
    cache_dir: Path = ROOT / '.cache'
    policy_path: Path = ROOT / 'data/policy/USGIC-CSCIndividualHealthInsurance_2017-2018.pdf'


def get_settings() -> Settings:
    # Read on demand so a newly saved local key does not require rebuilding the index.
    return Settings()
