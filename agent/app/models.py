"""Schemas (pydantic) shared by the config loader, the manager and the API."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ServerState(StrEnum):
    OFFLINE = "offline"
    STARTING = "starting"
    ONLINE = "online"
    STOPPING = "stopping"


class ServerConfig(BaseModel):
    """One entry of servers.yaml."""

    id: str
    name: str
    cwd: str
    command: list[str] = Field(min_length=1)
    port: int | None = None
    stop_timeout: float = 60
    start_timeout: float = 300


class ServerStatus(BaseModel):
    """What the API returns for a server."""

    id: str
    name: str
    state: ServerState
    pid: int | None = None
    started_at: datetime | None = None
    uptime_seconds: float | None = None
    last_error: str | None = None
