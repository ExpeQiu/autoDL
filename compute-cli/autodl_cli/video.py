"""视频任务参数：文生 / 单图 / 首尾帧 / 多图。Agent 与 CLI 共用。"""

from __future__ import annotations

from typing import Any

PLAY_MODES = ("text", "first_frame", "first_last_frame", "multi")
WORKFLOW_BY_PLAY = {
    "text": "t2v.u03",
    "first_frame": "t2v.i2v",
    "first_last_frame": "t2v.flf2v",
    "multi": "t2v.r2v",
}
MAX_REF_IMAGES = 9


class VideoRequestError(ValueError):
    """参数不满足对应玩法。"""


def _clean(values: list[str] | None) -> list[str]:
    return [item.strip() for item in (values or []) if item and item.strip()]


def resolve_video_request(
    *,
    modality: str,
    play: str | None,
    images: list[str] | None = None,
    end_image: str | None = None,
    images_csv: str | None = None,
) -> dict[str, Any]:
    """返回可交给编排的字段。非视频模态不带图。"""
    refs = _clean(images)
    if images_csv and images_csv.strip():
        refs.extend(part.strip() for part in images_csv.split("|") if part.strip())
    end = (end_image or "").strip() or None
    mode = (play or "").strip() or None

    if modality != "video":
        if mode or refs or end:
            raise VideoRequestError("参考图和 --play 只用于 --modality video")
        return {}

    if mode is None:
        if end and refs:
            mode = "first_last_frame"
        elif len(refs) >= 2:
            mode = "multi"
        elif len(refs) == 1:
            mode = "first_frame"
        elif end:
            raise VideoRequestError("首尾帧需要首帧和尾帧两张图")
        else:
            mode = "text"
    if mode not in WORKFLOW_BY_PLAY:
        raise VideoRequestError(f"不支持的视频模式: {mode}")

    if mode == "text":
        if refs or end:
            raise VideoRequestError("文生视频不要带参考图")
        return {"play_mode": mode, "workflow_id": WORKFLOW_BY_PLAY[mode]}

    if mode == "first_frame":
        if len(refs) != 1 or end:
            raise VideoRequestError("单图视频需要恰好 1 张 --image，不要 --end-image")
        return {
            "play_mode": mode,
            "workflow_id": WORKFLOW_BY_PLAY[mode],
            "image_ref": refs[0],
        }

    if mode == "first_last_frame":
        if len(refs) != 1 or not end:
            raise VideoRequestError("首尾帧需要 1 张 --image 和 1 张 --end-image")
        return {
            "play_mode": mode,
            "workflow_id": WORKFLOW_BY_PLAY[mode],
            "image_ref": refs[0],
            "end_image_ref": end,
        }

    if len(refs) < 2 or len(refs) > MAX_REF_IMAGES or end:
        raise VideoRequestError("多图视频需要 2 到 9 张 --image，不要 --end-image")
    return {
        "play_mode": mode,
        "workflow_id": WORKFLOW_BY_PLAY[mode],
        "image_refs": refs,
    }
