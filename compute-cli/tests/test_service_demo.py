from __future__ import annotations

from click.testing import CliRunner

from autodl_cli.cli import cli
from autodl_cli.orch import OrchError
from autodl_cli.utils.errors import EXIT_NOT_READY
from tests.util import load_envelope


def test_service_list_demo() -> None:
    result = CliRunner().invoke(cli, ["--demo", "service", "list", "--format", "json"])
    assert result.exit_code == 0, result.output
    data = load_envelope(result.output)
    assert data["module"] == "service.list"
    assert data["data_source"] == "demo"
    assert data["ok"] is True
    modalities = {item["modality"] for item in data["items"]}
    assert modalities == {"text", "image", "video"}
    ids = {item["id"] for item in data["items"]}
    assert ids == {"llm.chat", "t2i.demo", "t2v.u03"}
    assert all(item.get("exposed") is True for item in data["items"])
    assert all(item.get("invoke", {}).get("group") == "job" for item in data["items"])


def test_service_list_demo_filter() -> None:
    result = CliRunner().invoke(
        cli,
        ["--demo", "service", "list", "--modality", "image", "--exposed", "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    data = load_envelope(result.output)
    assert data["count"] == 1
    assert data["items"][0]["id"] == "t2i.demo"


def test_service_list_live(monkeypatch) -> None:
    monkeypatch.setenv("AUTODL_MOCK", "false")
    monkeypatch.setattr(
        "autodl_cli.orch.list_services",
        lambda **kwargs: [
            {
                "id": "llm.chat",
                "modality": "text",
                "label": "文本对话",
                "provider": "llm",
                "workflow_id": "llm.chat",
                "exposed": True,
            }
        ],
    )
    result = CliRunner().invoke(cli, ["service", "list", "--format", "json"])
    assert result.exit_code == 0, result.output
    data = load_envelope(result.output)
    assert data["data_source"] == "live"
    assert data["items"][0]["id"] == "llm.chat"


def test_service_list_orch_down(monkeypatch) -> None:
    monkeypatch.setenv("AUTODL_MOCK", "false")
    monkeypatch.setattr(
        "autodl_cli.orch.list_services",
        lambda **kwargs: (_ for _ in ()).throw(OrchError("编排不可达", EXIT_NOT_READY)),
    )
    result = CliRunner().invoke(cli, ["service", "list", "--format", "json"])
    assert result.exit_code == EXIT_NOT_READY
    data = load_envelope(result.output)
    assert data["ok"] is False
