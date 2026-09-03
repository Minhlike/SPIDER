import json
import os
import socket
import subprocess
import sys

import pytest
from spider import launcher

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows launcher")


@pytest.fixture
def launcher_files(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "DATA", tmp_path)
    monkeypatch.setattr(launcher, "STATE", tmp_path / "launcher.json")


def test_stale_pid_never_signals_unrelated_process(launcher_files):
    # Deliberately point state at this live test process but with another creation time.
    identity = launcher.process_identity(os.getpid())
    state = {**identity, "created": identity["created"] - 1, "root": str(launcher.ROOT),
             "stop_event": "Local\\SPIDER-nonexistent"}
    launcher.STATE.write_text(json.dumps(state))
    assert launcher.read_state() is None
    launcher.stop()
    assert launcher.process_identity(os.getpid()) == identity


def test_port_conflict_does_not_spawn_or_stop(monkeypatch, launcher_files):
    monkeypatch.setattr(launcher, "port_available", lambda: False)
    def forbidden(*args, **kwargs):
        pytest.fail("A foreign port occupant must be left alone")
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(launcher, "signal_stop", forbidden)
    with pytest.raises(RuntimeError, match="occupied"):
        launcher.start(False)


def test_repeat_start_reuses_exact_healthy_backend(monkeypatch, launcher_files):
    state = {**launcher.process_identity(os.getpid()), "root": str(launcher.ROOT)}
    launcher.STATE.write_text(json.dumps(state))
    monkeypatch.setattr(launcher, "healthy", lambda: True)
    opened = []
    monkeypatch.setattr(launcher.webbrowser, "open", opened.append)
    def forbidden(*args, **kwargs):
        pytest.fail("Duplicate launch")
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    assert launcher.start() == state
    assert opened == [launcher.URL]


def test_unhealthy_existing_process_does_not_open_browser(monkeypatch, launcher_files):
    state = {**launcher.process_identity(os.getpid()), "root": str(launcher.ROOT)}
    launcher.STATE.write_text(json.dumps(state))
    monkeypatch.setattr(launcher, "healthy", lambda: False)
    with pytest.raises(RuntimeError, match="not healthy"):
        launcher.start(False)
