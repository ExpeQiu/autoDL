from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from autodl_cli.cli import cli
from autodl_cli.orch import OrchError
from autodl_cli.utils.errors import EXIT_NOT_READY
from tests.util import load_envelope


def test_compute_health_live(monkeypatch) -> None:
    monkeypatch.setenv("AUTODL_MOCK", "false")
    monkeypatch.setattr(
        "autodl_cli.orch.compute_health",
        lambda: {
            "ok": True,
            "comfyui": {"ok": True, "provider": "mock"},
            "llm": {"ok": True, "provider": "mock"},
            "provider": "mixed",
        },
    )
    result = CliRunner().invoke(cli, ["compute", "health", "--format", "json"])
    assert result.exit_code == 0, result.output
    data = load_envelope(result.output)
    assert data["module"] == "compute.health"
    assert data["data_source"] == "live"
    assert data["ok"] is True
    assert data["items"][0]["comfyui"]["ok"] is True


def test_compute_health_orch_down(monkeypatch) -> None:
    monkeypatch.setenv("AUTODL_MOCK", "false")
    monkeypatch.setattr(
        "autodl_cli.orch.compute_health",
        lambda: (_ for _ in ()).throw(OrchError("编排不可达", EXIT_NOT_READY)),
    )
    result = CliRunner().invoke(cli, ["compute", "health", "--format", "json"])
    assert result.exit_code == EXIT_NOT_READY
    data = load_envelope(result.output)
    assert data["ok"] is False
    assert "编排不可达" in data["error"]


def test_job_submit_live(monkeypatch) -> None:
    monkeypatch.setenv("AUTODL_MOCK", "false")

    def fake_create(**kwargs):
        return {
            "id": "job_live1",
            "run_id": "run_live1",
            "modality": kwargs["modality"],
            "prompt": kwargs["prompt"],
            "status": "succeeded",
            "provider": "mock",
            "output_uri": "/tmp/x.svg",
        }

    monkeypatch.setattr("autodl_cli.orch.create_job", fake_create)
    result = CliRunner().invoke(
        cli,
        ["job", "submit", "--modality", "image", "--prompt", "p1", "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    data = load_envelope(result.output)
    assert data["data_source"] == "live"
    assert data["job_id"] == "job_live1"
    assert data["run_id"] == "run_live1"
    assert data["items"][0]["status"] == "succeeded"


def test_job_get_live(monkeypatch) -> None:
    monkeypatch.setenv("AUTODL_MOCK", "false")
    monkeypatch.setattr(
        "autodl_cli.orch.get_job",
        lambda job_id: {
            "id": job_id,
            "run_id": "run_x",
            "modality": "image",
            "status": "succeeded",
            "provider": "mock",
        },
    )
    result = CliRunner().invoke(cli, ["job", "get", "job_live1", "--format", "json"])
    assert result.exit_code == 0, result.output
    data = load_envelope(result.output)
    assert data["module"] == "job.get"
    assert data["data_source"] == "live"


def test_job_file_live(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTODL_MOCK", "false")
    dest = tmp_path / "out.svg"
    monkeypatch.setattr(
        "autodl_cli.orch.get_job",
        lambda job_id: {"id": job_id, "run_id": "run_x", "output_uri": "/remote/x.svg", "status": "succeeded"},
    )
    monkeypatch.setattr("autodl_cli.orch.download_file", lambda job_id, dest=None: dest.write_text("<svg/>") or dest)
    result = CliRunner().invoke(cli, ["job", "file", "job_live1", "-o", str(dest), "--format", "json"])
    assert result.exit_code == 0, result.output
    data = load_envelope(result.output)
    assert data["ok"] is True
    assert dest.is_file()
