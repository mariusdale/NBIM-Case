from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def load_app_env(root: Path) -> None:
    load_dotenv(root / ".env", override=True)


def get_env_secret(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip().lstrip("\ufeff")
    return value or None


def get_anthropic_api_key() -> str | None:
    value = get_env_secret("ANTHROPIC_API_KEY")
    if not value:
        return None
    if not value.startswith("sk-ant-"):
        return None
    return value
