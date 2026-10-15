import sys
from pathlib import Path

import pytest

from app.manager import ServerManager
from app.models import ServerConfig

FAKE_SERVER = Path(__file__).parent / "fake_server.py"


def fake_config(server_id: str = "fake", *flags: str, **overrides) -> ServerConfig:
    """A ServerConfig that runs tests/fake_server.py with the given flags."""
    values = {
        "id": server_id,
        "name": f"Fake {server_id}",
        "cwd": str(FAKE_SERVER.parent),
        "command": [sys.executable, str(FAKE_SERVER), "--start-delay", "0.2", *flags],
        "stop_timeout": 3,
        "start_timeout": 5,
    }
    values.update(overrides)
    return ServerConfig(**values)


@pytest.fixture
def make_manager(tmp_path):
    """Build a ServerManager from configs and stop leftover processes after the test."""
    managers: list[ServerManager] = []

    def _make(*configs: ServerConfig) -> ServerManager:
        manager = ServerManager({c.id: c for c in configs}, tmp_path / "logs")
        managers.append(manager)
        return manager

    yield _make

    for manager in managers:
        for rt in manager._runtimes.values():
            if rt.process and rt.process.returncode is None:
                rt.process.kill()
