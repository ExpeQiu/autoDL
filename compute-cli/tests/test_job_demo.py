from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from autodl_cli.cli import cli
from autodl_cli.envelope import make_envelope
from autodl_cli.store import create_demo_job, get_job
from tests.util import load_envelope


def test_envelope_keys() -> None:
    env = make_envelope(module="job.submit", data_source="demo", ok=True, items=[{"id": "1"}])
    assert env["module"] == "job.submit"
    assert env["data_source"] == "demo"
    assert env["ok"] is True
    assert env["count"] == 1
    assert env["version"]


def test_create_demo_job_image(tmp_path: Path, monkeypatch) -> None:
    import autodl_cli.store as store

    monkeypatch.setattr(store, "STORE_PATH", tmp_path / "jobs.json")
    monkeypatch.setattr(store, "ARTIFACTS", tmp_path / "artifacts")
    job = create_demo_job(modality="image", prompt="一只猫")
    assert job["status"] == "succeeded"
    assert job["provider"] == "mock"
    assert Path(job["output_uri"]).is_file()
    assert get_job(job["id"])["id"] == job["id"]


def test_job_submit_demo_cli() -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--demo", "job", "submit", "--modality", "image", "--prompt", "一只猫", "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    data = load_envelope(result.output)
    assert data["module"] == "job.submit"
    assert data["data_source"] == "demo"
    assert data["ok"] is True
    assert data["job_id"].startswith("job_")
    assert data["items"][0]["status"] == "succeeded"
    assert data["items"][0]["output_uri"]


def test_config_check_redacts_secrets() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--demo", "config", "check", "--format", "json"])
    assert result.exit_code == 0, result.output
    data = load_envelope(result.output)
    snap = data["items"][0]
    assert "token_set" in snap
    assert "AUTODL_TOKEN" not in json.dumps(data)
    assert "wpIXc" not in result.output


def test_power_on_blocked_without_allow(monkeypatch) -> None:
    monkeypatch.setenv("AUTODL_ALLOW_POWER", "false")
    runner = CliRunner()
    result = runner.invoke(cli, ["instance", "power-on", "--demo", "--format", "json"])
    assert result.exit_code == 1
    data = load_envelope(result.output)
    assert data["ok"] is False


def test_format_after_subcommand() -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["job", "submit", "--modality", "text", "--prompt", "hi", "--demo", "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    data = load_envelope(result.output)
    assert data["module"] == "job.submit"
