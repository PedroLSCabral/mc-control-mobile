"""ServerManager tests with the fake server. These guide your implementation:
run `pytest tests/test_manager.py -x` and make them pass one by one, top to bottom.
"""

import pytest
from conftest import fake_config

from app.manager import ConflictError, ServerNotFoundError
from app.models import ServerState

# ---------- step 1: start ----------


async def test_starts_offline(make_manager):
    manager = make_manager(fake_config())
    assert manager.status("fake").state is ServerState.OFFLINE


async def test_unknown_server(make_manager):
    manager = make_manager(fake_config())
    with pytest.raises(ServerNotFoundError):
        manager.status("nope")


async def test_start_goes_starting_then_online(make_manager):
    manager = make_manager(fake_config())
    status = await manager.start("fake")
    assert status.state is ServerState.STARTING
    assert status.pid is not None

    await manager.wait_for_state("fake", ServerState.ONLINE, timeout=5)
    assert manager.status("fake").uptime_seconds >= 0


async def test_start_writes_log_file(make_manager, tmp_path):
    manager = make_manager(fake_config())
    await manager.start("fake")
    await manager.wait_for_state("fake", ServerState.ONLINE, timeout=5)
    log = (tmp_path / "logs" / "fake.log").read_text(encoding="utf-8")
    assert "Done (" in log


async def test_start_twice_is_conflict(make_manager):
    manager = make_manager(fake_config())
    await manager.start("fake")
    with pytest.raises(ConflictError):
        await manager.start("fake")


# ---------- step 2: stop ----------


async def test_graceful_stop(make_manager):
    manager = make_manager(fake_config())
    await manager.start("fake")
    await manager.wait_for_state("fake", ServerState.ONLINE, timeout=5)

    status = await manager.stop("fake")
    assert status.state is ServerState.STOPPING

    await manager.wait_for_state("fake", ServerState.OFFLINE, timeout=5)
    status = manager.status("fake")
    assert status.pid is None
    assert status.last_error is None  # stopped on request: not an error


async def test_stop_when_offline_is_conflict(make_manager):
    manager = make_manager(fake_config())
    with pytest.raises(ConflictError):
        await manager.stop("fake")


async def test_can_start_again_after_stop(make_manager):
    manager = make_manager(fake_config())
    await manager.start("fake")
    await manager.wait_for_state("fake", ServerState.ONLINE, timeout=5)
    await manager.stop("fake")
    await manager.wait_for_state("fake", ServerState.OFFLINE, timeout=5)

    await manager.start("fake")
    await manager.wait_for_state("fake", ServerState.ONLINE, timeout=5)


# ---------- step 3: when things go wrong ----------


async def test_stop_timeout_kills_process(make_manager):
    manager = make_manager(fake_config("fake", "--ignore-stop", stop_timeout=0.5))
    await manager.start("fake")
    await manager.wait_for_state("fake", ServerState.ONLINE, timeout=5)
    await manager.stop("fake")

    await manager.wait_for_state("fake", ServerState.OFFLINE, timeout=5)
    assert manager.status("fake").last_error is not None


async def test_crash_while_starting_goes_offline_with_error(make_manager):
    manager = make_manager(fake_config("fake", "--crash-after", "0.2"))
    await manager.start("fake")
    await manager.wait_for_state("fake", ServerState.OFFLINE, timeout=5)
    assert manager.status("fake").last_error is not None


async def test_start_timeout_kills_process(make_manager):
    manager = make_manager(fake_config("fake", "--never-ready", start_timeout=0.5))
    await manager.start("fake")
    await manager.wait_for_state("fake", ServerState.OFFLINE, timeout=5)
    assert manager.status("fake").last_error is not None


async def test_servers_are_independent(make_manager):
    manager = make_manager(fake_config("a"), fake_config("b"))
    await manager.start("a")
    await manager.wait_for_state("a", ServerState.ONLINE, timeout=5)
    assert manager.status("b").state is ServerState.OFFLINE
