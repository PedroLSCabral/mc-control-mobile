"""Loads settings from environment variables and servers from servers.yaml."""

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.models import ServerConfig


@dataclass(frozen=True)
class Settings:
    token: str
    servers_file: Path
    log_dir: Path

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.environ.get("MC_AGENT_TOKEN", "")
        if not token:
            raise RuntimeError("MC_AGENT_TOKEN não definido. Veja .env.example.")
        return cls(
            token=token,
            servers_file=Path(os.environ.get("MC_AGENT_SERVERS", "servers.yaml")),
            log_dir=Path(os.environ.get("MC_AGENT_LOG_DIR", "logs")),
        )


def load_servers(path: Path) -> dict[str, ServerConfig]:
    """Read servers.yaml and return {server_id: ServerConfig}."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    servers = data.get("servers") or {}
    return {sid: ServerConfig(id=sid, **cfg) for sid, cfg in servers.items()}
