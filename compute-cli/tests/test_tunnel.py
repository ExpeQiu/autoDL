from __future__ import annotations

import pytest
from click.testing import CliRunner

from autodl_cli.cli import cli
from autodl_cli.tunnel import TunnelError, _ssh_cmd
from autodl_cli.utils.errors import EXIT_ERROR, EXIT_NOT_READY
from tests.util import load_envelope


def test_tunnel_demo_status_start_stop() -> None:
    runner = CliRunner()
    status = runner.invoke(cli, ["--demo", "tunnel", "status", "--format", "json"])
    assert status.exit_code == 0, status.output
    data = load_envelope(status.output)
    assert data["module"] == "tunnel.status"
    assert data["ok"] is True
    start = runner.invoke(cli, ["tunnel", "start", "--demo", "--format", "json"])
    assert start.exit_code == 0, start.output
    assert load_envelope(start.output)["ok"] is True
    stop = runner.invoke(cli, ["tunnel", "stop", "--demo", "--format", "json"])
    assert stop.exit_code == 0
    assert load_envelope(stop.output)["items"][0]["stopped"] is True


def test_tunnel_status_live_down(monkeypatch) -> None:
    monkeypatch.setenv("AUTODL_MOCK", "false")
    monkeypatch.setattr("autodl_cli.tunnel.port_listening", lambda *a, **k: False)
    monkeypatch.setattr("autodl_cli.tunnel._pid", lambda: None)
    result = CliRunner().invoke(cli, ["tunnel", "status", "--format", "json"])
    assert result.exit_code == EXIT_NOT_READY
    data = load_envelope(result.output)
    assert data["data_source"] == "live"
    assert data["ok"] is False


def test_tunnel_status_live_up(monkeypatch) -> None:
    monkeypatch.setenv("AUTODL_MOCK", "false")
    monkeypatch.setattr("autodl_cli.tunnel.port_listening", lambda *a, **k: True)
    monkeypatch.setattr("autodl_cli.tunnel._pid", lambda: 4242)
    result = CliRunner().invoke(cli, ["tunnel", "status", "--format", "json"])
    assert result.exit_code == 0, result.output
    data = load_envelope(result.output)
    assert data["ok"] is True
    assert data["items"][0]["listening"] is True
    assert "wpIXc" not in result.output


def test_ssh_cmd_requires_port(monkeypatch) -> None:
    monkeypatch.setenv("COMFYUI_SSH_PORT", "")
    with pytest.raises(TunnelError) as exc:
        _ssh_cmd()
    assert exc.value.code == EXIT_ERROR
    assert "COMFYUI_SSH_PORT" in str(exc.value)


def test_tunnel_start_live_no_port(monkeypatch) -> None:
    monkeypatch.setenv("AUTODL_MOCK", "false")
    monkeypatch.setenv("COMFYUI_SSH_PORT", "")
    result = CliRunner().invoke(cli, ["tunnel", "start", "--format", "json"])
    assert result.exit_code == EXIT_ERROR
    data = load_envelope(result.output)
    assert data["ok"] is False
    assert "COMFYUI_SSH_PORT" in data["error"]
    assert "wpIXc" not in result.output
