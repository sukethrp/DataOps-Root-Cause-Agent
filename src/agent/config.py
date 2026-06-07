"""Agent configuration loaded from environment."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from pydantic import BaseModel, Field


class Settings(BaseModel):
    """Foundry and Foundry IQ connection settings."""

    project_endpoint: str = Field(min_length=1)
    search_endpoint: str = Field(min_length=1)
    knowledge_base_name: str = Field(min_length=1)
    kb_mcp_endpoint: str = Field(min_length=1)
    model_name: str = Field(min_length=1)

    @classmethod
    def from_env(cls, *, dotenv_path: str | None = None) -> Settings:
        load_dotenv(dotenv_path)
        return cls(
            project_endpoint=_require_env("PROJECT_ENDPOINT"),
            search_endpoint=_require_env("SEARCH_ENDPOINT"),
            knowledge_base_name=_require_env("KNOWLEDGE_BASE_NAME"),
            kb_mcp_endpoint=_require_env("KB_MCP_ENDPOINT"),
            model_name=_require_env("MODEL_NAME"),
        )


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        msg = f"Missing required environment variable: {name}"
        raise ValueError(msg)
    return value
