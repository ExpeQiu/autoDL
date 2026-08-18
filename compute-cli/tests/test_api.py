from __future__ import annotations

from click.testing import CliRunner

from autodl_cli.api import _scrub
from autodl_cli.cli import cli
from autodl_cli.utils.errors import EXIT_AUTH, EXIT_ERROR, EXIT_NOT_READY
from tests.util import load_envelope


def test_scrub_drops_secrets() -> None:
    raw = {"proxy_host": "connect.westc.seetacloud.com", "ssh_port": 30856, "root_password": "secret", "jupyter_token": "abc"}
    clean = _scrub(raw)
    assert "root_password" not in clean
    assert "jupyter_token" not in clean
    assert clean["ssh_port"] == 30856


def test_instance_list_demo() -> None:
    result = CliRunner().invoke(cli, ["--demo", "instance", "list", "--format", "json"])
    assert result.exit_code == 0, result.output
    data = load_envelope(result.output)
    assert data["module"] == "instance.list"
    assert data["items"][0]["status"] == "running"


def test_wallet_demo() -> None:
    result = CliRunner().invoke(cli, ["wallet", "balance", "--demo", "--format", "json"])
    assert result.exit_code == 0
    data = load_envelope(result.output)
    assert data["items"][0]["yuan"] == 1.0


def test_wallet_live_no_token(monkeypatch) -> None:
    monkeypatch.setenv("AUTODL_MOCK", "false")
    monkeypatch.setenv("AUTODL_TOKEN", "")
    result = CliRunner().invoke(cli, ["wallet", "balance", "--format", "json"])
    assert result.exit_code == EXIT_AUTH
    data = load_envelope(result.output)
    assert data["ok"] is False
    assert "AUTODL_TOKEN" in data["error"]


def test_instance_status_live_shutdown(monkeypatch) -> None:
    monkeypatch.setenv("AUTODL_MOCK", "false")
    monkeypatch.setenv("AUTODL_TOKEN", "tok")
    monkeypatch.setattr(
        "autodl_cli.api.describe",
        lambda uuid=None: {"uuid": "pro-x", "name": "gpu", "status": "shutdown", "ssh_host": None, "ssh_port": None},
    )
    result = CliRunner().invoke(cli, ["instance", "status", "--format", "json"])
    assert result.exit_code == EXIT_NOT_READY
    data = load_envelope(result.output)
    assert data["ok"] is False
    assert data["items"][0]["status"] == "shutdown"


def test_instance_list_live(monkeypatch) -> None:
    monkeypatch.setenv("AUTODL_MOCK", "false")
    monkeypatch.setenv("AUTODL_TOKEN", "tok")
    monkeypatch.setattr(
        "autodl_cli.api.list_instances",
        lambda: [{"uuid": "pro-x", "name": "gpu", "status": "running", "gpu": "5090-p"}],
    )
    result = CliRunner().invoke(cli, ["instance", "list", "--format", "json"])
    assert result.exit_code == 0, result.output
    data = load_envelope(result.output)
    assert data["data_source"] == "live"
    assert data["items"][0]["uuid"] == "pro-x"
    assert "secret" not in result.output
    assert "wpIXc" not in result.output


def test_power_on_live_blocked(monkeypatch) -> None:
    monkeypatch.setenv("AUTODL_MOCK", "false")
    monkeypatch.setenv("AUTODL_ALLOW_POWER", "false")
    monkeypatch.setenv("AUTODL_TOKEN", "tok")
    result = CliRunner().invoke(cli, ["instance", "power-on", "--format", "json"])
    assert result.exit_code == EXIT_ERROR
    data = load_envelope(result.output)
    assert data["ok"] is False
