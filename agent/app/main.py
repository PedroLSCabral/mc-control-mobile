"""HTTP API. Run with: uvicorn app.main:create_app --factory"""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from app.auth import require_token
from app.config import Settings, load_servers
from app.manager import ConflictError, ServerManager, ServerNotFoundError
from app.models import ServerStatus


def create_app(manager: ServerManager | None = None, token: str | None = None) -> FastAPI:
    """Build the app. Tests pass `manager` and `token`; production reads them from env."""
    if manager is None or token is None:
        settings = Settings.from_env()
        manager = manager or ServerManager(load_servers(settings.servers_file), settings.log_dir)
        token = token or settings.token

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await manager.shutdown()

    app = FastAPI(title="MC Control Agent", version="0.1.0", lifespan=lifespan)
    app.state.manager = manager
    app.state.token = token

    @app.exception_handler(ServerNotFoundError)
    async def _not_found(_: Request, exc: ServerNotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ConflictError)
    async def _conflict(_: Request, exc: ConflictError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.get("/health")
    async def health() -> dict:
        return {"ok": True}

    auth = [Depends(require_token)]

    @app.get("/servers", dependencies=auth)
    async def list_servers() -> list[ServerStatus]:
        return manager.list()

    @app.get("/servers/{server_id}", dependencies=auth)
    async def get_server(server_id: str) -> ServerStatus:
        return manager.status(server_id)

    @app.post("/servers/{server_id}/start", dependencies=auth)
    async def start_server(server_id: str) -> ServerStatus:
        return await manager.start(server_id)

    @app.post("/servers/{server_id}/stop", dependencies=auth)
    async def stop_server(server_id: str) -> ServerStatus:
        return await manager.stop(server_id)

    return app
