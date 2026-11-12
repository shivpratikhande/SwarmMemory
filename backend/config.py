"""Runtime configuration. All secrets come from environment variables (or a local .env)."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- core ---
    swarm_mode: Literal["demo", "testnet"] = "demo"
    database_url: str = "postgresql+psycopg://localhost:5432/swarmmemory"
    server_secret: str = Field(default="dev-only-change-me", min_length=8)
    api_base_url: str = "http://127.0.0.1:8000"  # used by agents to reach the SwarmMemory API
    cors_origins: str = "http://localhost:3000"

    # --- embeddings ---
    embedding_dim: int = 256
    embedding_provider: Literal["local", "openai"] = "local"
    embedding_api_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = ""

    # --- NEAR ---
    near_network_id: str = "testnet"
    near_rpc_url: str = "https://rpc.testnet.fastnear.com"
    near_explorer_url: str = "https://testnet.nearblocks.io"
    near_contract_id: str = ""
    near_owner_account_id: str = ""  # contract owner = reputation oracle
    near_owner_private_key: str = ""
    near_researcher_account_id: str = ""
    near_researcher_private_key: str = ""
    near_verifier_account_id: str = ""
    near_verifier_private_key: str = ""
    near_developer_account_id: str = ""
    near_developer_private_key: str = ""
    near_credentials_dir: str = ""  # optional: ~/.near-credentials/testnet
    near_tx_timeout_s: float = 60.0

    # --- marketplace ---
    default_memory_price_near: str = "0.01"

    @property
    def is_testnet(self) -> bool:
        return self.swarm_mode == "testnet"

    @property
    def network_label(self) -> str:
        return "testnet" if self.is_testnet else "simulated"


@lru_cache
def get_settings() -> Settings:
    return Settings()
