"""Lifecycle of the game servers: start, stop and state tracking.

State machine (one per server):

    offline --start--> starting --"Done" in log--> online --stop--> stopping --exit--> offline
       ^                  |  timeout / process died                    |  timeout -> kill
       +------------------+-----------------------------------------------+

Processes are started with asyncio's version of Popen (`asyncio.create_subprocess_exec`):
same idea as `subprocess.Popen`, but reading stdout and waiting for exit don't block the
event loop that serves the HTTP requests.
"""

import asyncio
import re
from collections.abc import Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.models import ServerConfig, ServerState, ServerStatus

# Vanilla, Paper, Forge and NeoForge all print this when the server is ready.
DONE_PATTERN = re.compile(r"Done \(\d")


class ServerNotFoundError(Exception):
    pass


class ConflictError(Exception):
    """The action does not make sense in the current state (e.g. start while online)."""


@dataclass
class _Runtime:
    """Everything the manager knows about one server while the agent is running."""

    config: ServerConfig
    state: ServerState = ServerState.OFFLINE
    process: asyncio.subprocess.Process | None = None
    started_at: datetime | None = None
    last_error: str | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    tasks: set[asyncio.Task] = field(default_factory=set)


class ServerManager:
    def __init__(self, servers: dict[str, ServerConfig], log_dir: Path) -> None:
        self._runtimes = {sid: _Runtime(cfg) for sid, cfg in servers.items()}
        self._log_dir = log_dir

    # ---------- queries ----------

    def list(self) -> list[ServerStatus]:
        return [self.status(sid) for sid in self._runtimes]

    def status(self, server_id: str) -> ServerStatus:
        rt = self._get(server_id)
        uptime = None
        if rt.started_at and rt.state is not ServerState.OFFLINE:
            uptime = (datetime.now(UTC) - rt.started_at).total_seconds()
        return ServerStatus(
            id=rt.config.id,
            name=rt.config.name,
            state=rt.state,
            pid=rt.process.pid if rt.process else None,
            started_at=rt.started_at,
            uptime_seconds=uptime,
            last_error=rt.last_error,
        )

    async def wait_for_state(self, server_id: str, state: ServerState, timeout: float) -> None:
        """Wait until the server reaches `state`. Raises TimeoutError otherwise."""
        rt = self._get(server_id)
        async with asyncio.timeout(timeout):
            while rt.state is not state:
                await asyncio.sleep(0.05)

    # ---------- actions ----------

    async def start(self, server_id: str) -> ServerStatus:
        """Launch the server process and return right away with state `starting`.

        Background tasks then move the state to `online` (when "Done" shows up in the
        output) or back to `offline` (process died or start_timeout expired).
        """
        rt = self._get(server_id)  # noqa: F841 (apague o noqa ao implementar)
        # TODO(Pedro) passo 1. Roteiro:
        #  1. Entre no lock do servidor (`async with rt.lock:`), para que dois pedidos
        #     simultâneos não liguem o mesmo servidor duas vezes.
        #  2. Se o estado não for OFFLINE, lance ConflictError com uma mensagem clara.
        #  3. Crie o processo com `await asyncio.create_subprocess_exec(*cfg.command, ...)`,
        #     passando cwd=cfg.cwd, stdin=PIPE, stdout=PIPE e stderr=STDOUT
        #     (as constantes ficam em `asyncio.subprocess`). Guarde-o em rt.process.
        #  4. Atualize rt.state, rt.started_at (`datetime.now(UTC)`) e limpe rt.last_error.
        #  5. Coloque os vigias para rodar em segundo plano com `self._spawn(...)`:
        #     `_watch_output` e `_watch_start_timeout`.
        #  6. Fora do lock, retorne `self.status(server_id)`.
        raise NotImplementedError

    async def stop(self, server_id: str) -> ServerStatus:
        """Ask the server to stop and return right away with state `stopping`.

        A background task sends `stop`, waits up to stop_timeout and kills the process
        if it is still alive. The output watcher sets `offline` when the process exits.
        """
        rt = self._get(server_id)  # noqa: F841 (apague o noqa ao implementar)
        # TODO(Pedro) passo 2. Roteiro:
        #  1. Use o lock, como no start.
        #  2. Só faz sentido parar se o estado for STARTING ou ONLINE; senão, ConflictError.
        #  3. Mude o estado para STOPPING e rode `_graceful_stop` em segundo plano.
        #  4. Retorne o status. Não espere o processo morrer aqui: o app recebe a resposta
        #     na hora e acompanha o estado consultando GET /servers/{id}.
        raise NotImplementedError

    async def shutdown(self) -> None:
        """Called when the agent exits: cancel background tasks (servers are left alone)."""
        for rt in self._runtimes.values():
            for task in list(rt.tasks):
                task.cancel()

    # ---------- background tasks ----------

    async def _watch_output(self, rt: _Runtime, proc: asyncio.subprocess.Process) -> None:
        """Copy the process output to logs/<id>.log, detect "Done", handle the exit."""
        # TODO(Pedro) passo 1. Roteiro:
        #  1. Garanta que self._log_dir existe e abra `<log_dir>/<id>.log` em modo "a".
        #  2. `async for raw in proc.stdout:` entrega uma linha (bytes) por vez até o
        #     processo fechar a saída. Decodifique, grave no log e dê flush.
        #  3. Se o estado for STARTING e DONE_PATTERN.search(linha), mude para ONLINE.
        #  4. Quando o loop acabar, o processo terminou: pegue o código com
        #     `await proc.wait()`.
        #  5. Se ninguém pediu para parar (estado diferente de STOPPING) e ainda não houver
        #     erro registrado, preencha rt.last_error dizendo que o processo caiu.
        #  6. Estado OFFLINE e rt.process = None.
        raise NotImplementedError

    async def _watch_start_timeout(self, rt: _Runtime, proc: asyncio.subprocess.Process) -> None:
        """Kill the process if it is still `starting` after start_timeout seconds."""
        # TODO(Pedro) passo 3. Dica: `await asyncio.sleep(...)` e depois confira se
        # `rt.process is proc` (pode ser outro processo, se reiniciaram no meio) e se o
        # estado ainda é STARTING. Se for, registre o motivo em rt.last_error e `proc.kill()`.
        # O _watch_output percebe a morte e cuida do resto.
        raise NotImplementedError

    async def _graceful_stop(self, rt: _Runtime, proc: asyncio.subprocess.Process) -> None:
        """Send `stop`, wait up to stop_timeout, then kill."""
        # TODO(Pedro) passo 2. Roteiro:
        #  1. Escreva b"stop\n" em proc.stdin e `await proc.stdin.drain()`. Se o processo já
        #     morreu, isso lança BrokenPipeError ou ConnectionResetError: ignore.
        #  2. `await asyncio.wait_for(proc.wait(), timeout=...)` espera a saída com limite.
        #  3. Se estourar (TimeoutError), registre o motivo em rt.last_error e `proc.kill()`.
        #     Passo 3: é aqui que o teste test_stop_timeout_kills_process entra.
        raise NotImplementedError

    # ---------- helpers ----------

    def _get(self, server_id: str) -> _Runtime:
        try:
            return self._runtimes[server_id]
        except KeyError:
            raise ServerNotFoundError(f"Servidor '{server_id}' não existe.") from None

    def _spawn(self, rt: _Runtime, coro: Coroutine) -> None:
        """Run `coro` in the background and keep a reference so it isn't garbage-collected."""
        task = asyncio.create_task(coro)
        rt.tasks.add(task)
        task.add_done_callback(rt.tasks.discard)
