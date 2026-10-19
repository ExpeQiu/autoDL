from __future__ import annotations

import base64
from pathlib import Path

from click.testing import CliRunner

from autodl_cli.cli import cli
from autodl_cli.video import VideoRequestError, resolve_video_request, video_controls
from tests.util import load_envelope

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_resolve_four_plays() -> None:
    assert resolve_video_request(modality="video", play="text")["workflow_id"] == "t2v.u03"
    one = resolve_video_request(modality="video", play="first_frame", images=["a.png"])
    assert one["workflow_id"] == "t2v.i2v"
    assert one["image_ref"] == "a.png"
    both = resolve_video_request(
        modality="video", play="first_last_frame", images=["a.png"], end_image="b.png"
    )
    assert both["workflow_id"] == "t2v.flf2v"
    assert both["end_image_ref"] == "b.png"
    many = resolve_video_request(modality="video", play=None, images_csv="a.png|b.png|c.png")
    assert many["play_mode"] == "multi"
    assert many["workflow_id"] == "t2v.r2v"
    assert many["image_refs"] == ["a.png", "b.png", "c.png"]


def test_controls_bounds() -> None:
    assert video_controls(width=1344, height=768, steps=4) == {"width": 1344, "height": 768, "steps": 4}
    assert video_controls() == {}
    try:
        video_controls(steps=9)
    except VideoRequestError as exc:
        assert "1–8" in str(exc)
    else:
        raise AssertionError("expected error")


def test_cli_passes_steps(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--demo", "job", "submit", "--modality", "video", "--play", "text", "--prompt", "海边", "--steps", "4", "--width", "1344", "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    item = load_envelope(result.output)["items"][0]
    assert item["steps"] == 4
    assert item["width"] == 1344


def test_resolve_rejects_bad_counts() -> None:
    try:
        resolve_video_request(modality="video", play="first_last_frame", images=["a.png"])
    except VideoRequestError as exc:
        assert "尾帧" in str(exc)
    else:
        raise AssertionError("expected error")
    try:
        resolve_video_request(modality="video", play="multi", images=["only.png"])
    except VideoRequestError as exc:
        assert "2" in str(exc)
    else:
        raise AssertionError("expected error")


def test_cli_video_modes(tmp_path: Path) -> None:
    first = tmp_path / "first.png"
    last = tmp_path / "last.png"
    extra = tmp_path / "extra.png"
    first.write_bytes(PNG)
    last.write_bytes(PNG)
    extra.write_bytes(PNG)
    runner = CliRunner()

    text = runner.invoke(
        cli,
        ["--demo", "job", "submit", "--modality", "video", "--play", "text", "--prompt", "海边", "--format", "json"],
    )
    assert text.exit_code == 0, text.output
    assert load_envelope(text.output)["items"][0]["workflow_id"] == "t2v.u03"

    single = runner.invoke(
        cli,
        [
            "--demo",
            "job",
            "submit",
            "--modality",
            "video",
            "--play",
            "first_frame",
            "--image",
            str(first),
            "--prompt",
            "镜头推进",
            "--format",
            "json",
        ],
    )
    assert single.exit_code == 0, single.output
    body = load_envelope(single.output)
    assert body["items"][0]["workflow_id"] == "t2v.i2v"
    assert body["items"][0]["play_mode"] == "first_frame"
    assert "base64" not in single.output

    flf = runner.invoke(
        cli,
        [
            "--demo",
            "job",
            "submit",
            "--modality",
            "video",
            "--play",
            "first_last_frame",
            "--image",
            str(first),
            "--end-image",
            str(last),
            "--prompt",
            "白天到夜晚",
            "--format",
            "json",
        ],
    )
    assert flf.exit_code == 0, flf.output
    assert load_envelope(flf.output)["items"][0]["workflow_id"] == "t2v.flf2v"

    multi = runner.invoke(
        cli,
        [
            "--demo",
            "job",
            "submit",
            "--modality",
            "video",
            "--play",
            "multi",
            "--images",
            f"{first}|{last}|{extra}",
            "--prompt",
            "<Picture 1> 走向 <Picture 2>",
            "--format",
            "json",
        ],
    )
    assert multi.exit_code == 0, multi.output
    assert load_envelope(multi.output)["items"][0]["workflow_id"] == "t2v.r2v"

    missing = runner.invoke(
        cli,
        ["--demo", "job", "submit", "--modality", "video", "--play", "first_frame", "--prompt", "缺图", "--format", "json"],
    )
    assert missing.exit_code == 1
    assert load_envelope(missing.output)["ok"] is False
