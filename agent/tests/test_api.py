"""API tests. They use a stub manager, so they pass before ServerManager is implemented."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.manager import ConflictError, ServerNotFoundError
from app.models import ServerState, ServerStatus

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class StubManager:
    def __init__(self):
        self.state = ServerState.OFFLINE

    def _status(self):
        return ServerStatus(id="fake", name="Fake", state=self.state)

    def list(self):
        return [self._status()]

    def status(self, server_id):
        if server_id != "fake":
            raise ServerNotFoundError(f"Servidor '{server_id}' não existe.")
        return self._status()

    async def start(self, server_id):
        self.status(server_id)
        if self.state is not ServerState.OFFLINE:
            raise ConflictError("já ligado")
        self.state = ServerState.STARTING
        return self._status()

    async def stop(self, server_id):
        self.status(server_id)
        self.state = ServerState.STOPPING
        return self._status()

    async def shutdown(self):
        pass


@pytest.fixture
def client():
    with TestClient(create_app(manager=StubManager(), token=TOKEN)) as c:
        yield c


def test_health_needs_no_token(client):
    assert client.get("/health").json() == {"ok": True}


@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "Bearer errado"}, {"Authorization": TOKEN}]
)
def test_rejects_missing_or_wrong_token(client, headers):
    assert client.get("/servers", headers=headers).status_code == 401


def test_list_servers(client):
    body = client.get("/servers", headers=AUTH).json()
    assert body[0]["id"] == "fake"
    assert body[0]["state"] == "offline"


def test_unknown_server_is_404(client):
    assert client.get("/servers/nope", headers=AUTH).status_code == 404


def test_start_then_start_again_is_409(client):
    assert client.post("/servers/fake/start", headers=AUTH).json()["state"] == "starting"
    assert client.post("/servers/fake/start", headers=AUTH).status_code == 409


def test_stop(client):
    assert client.post("/servers/fake/stop", headers=AUTH).json()["state"] == "stopping"
