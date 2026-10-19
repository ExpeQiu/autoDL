from __future__ import annotations

import base64
import functools
import logging
import shutil
from pathlib import Path
from typing import Any

import click

from autodl_cli.__version__ import __version__
from autodl_cli.config import (
    allow_power,
    comfyui_endpoint,
    config_snapshot,
    instance_uuid,
    is_mock,
    llm_base_url,
    load_env,
    orch_base,
    ssh_host,
    ssh_port,
)
from autodl_cli.envelope import emit, make_envelope
from autodl_cli.store import create_demo_job, get_job, list_jobs
from autodl_cli.catalog import demo_items
from autodl_cli.utils.errors import EXIT_AUTH, EXIT_COMPUTE_FAIL, EXIT_ERROR, EXIT_NOT_READY, EXIT_OK
from autodl_cli.utils.logger import setup_logger
from autodl_cli import orch
from autodl_cli import tunnel as tun
from autodl_cli.video import PLAY_MODES, VideoRequestError, resolve_video_request, video_controls
from autodl_cli import api as autodl_api

log = logging.getLogger("autodl")

_MODALITY = ("text", "image", "video")


def _source(demo: bool) -> str:
    return "demo" if is_mock(demo) else "live"


def _done(ctx: click.Context, envelope: dict[str, Any], code: int) -> None:
    emit(envelope, ctx.obj["fmt"])
    ctx.exit(code)


def _require_demo_or_p1(ctx: click.Context, demo: bool, module: str) -> str:
    if is_mock(demo):
        return "demo"
    env = make_envelope(
        module=module,
        data_source="live",
        ok=False,
        items=[],
        error="P1 真算力未启用；请加 --demo 或设 AUTODL_MOCK=true",
    )
    log.warning("live_blocked", extra={"cmd": module, "status": "blocked"})
    _done(ctx, env, EXIT_ERROR)
    raise AssertionError("unreachable")


def _require_power(ctx: click.Context, module: str) -> None:
    if allow_power():
        return
    env = make_envelope(
        module=module,
        data_source="live",
        ok=False,
        items=[],
        error="开机/关机需 AUTODL_ALLOW_POWER=true",
    )
    log.warning("power_blocked", extra={"cmd": module, "status": "blocked"})
    _done(ctx, env, EXIT_ERROR)


def _live(ctx: click.Context) -> bool:
    return not is_mock(bool(ctx.obj.get("demo")))


def _fail_orch(ctx: click.Context, module: str, exc: orch.OrchError) -> None:
    job_id = None
    if isinstance(exc.payload, dict):
        job_id = exc.payload.get("id")
    log.warning(
        "orch_error",
        extra={"cmd": module, "status": "error", "job_id": job_id},
    )
    _done(
        ctx,
        make_envelope(
            module=module,
            data_source="live",
            ok=False,
            items=[exc.payload] if isinstance(exc.payload, dict) else [],
            job_id=job_id,
            error=str(exc),
        ),
        exc.code,
    )


def _fail_api(ctx: click.Context, module: str, exc: autodl_api.ApiError) -> None:
    log.warning("api_error", extra={"cmd": module, "status": "error"})
    _done(
        ctx,
        make_envelope(module=module, data_source="live", ok=False, items=[], error=str(exc)),
        exc.code,
    )


def _demo_instance(status: str = "running") -> dict[str, Any]:
    return {
        "uuid": instance_uuid() or "pro-demo000000",
        "name": "demo-gpu",
        "status": status,
        "ssh_host": ssh_host(),
        "ssh_port": (ssh_port() or "22") if status == "running" else None,
        "gpu": "RTX 5090",
    }


def _emit_job(
    ctx: click.Context,
    module: str,
    job_row: dict[str, Any],
    data_source: str,
    *,
    kind: str = "submit",
) -> None:
    status = job_row.get("status")
    log.info(
        "job_event",
        extra={
            "cmd": module,
            "run_id": job_row.get("run_id"),
            "job_id": job_row.get("id"),
            "modality": job_row.get("modality"),
            "provider": job_row.get("provider"),
            "status": status,
        },
    )
    if kind == "get":
        ok, code = True, EXIT_OK
    elif kind == "wait":
        ok = status == "succeeded"
        code = EXIT_OK if ok else EXIT_COMPUTE_FAIL
    else:
        ok = status != "failed"
        code = EXIT_OK if ok else EXIT_COMPUTE_FAIL
    _done(
        ctx,
        make_envelope(
            module=module,
            data_source=data_source,
            ok=ok,
            items=[job_row],
            run_id=job_row.get("run_id"),
            job_id=job_row.get("id"),
        ),
        code,
    )


class IoGroup(click.Group):
    """子命令也接受 --format / --demo，方便智能体写在命令末尾。"""

    def add_command(self, cmd: click.Command, name: str | None = None) -> None:
        if not isinstance(cmd, click.Group):
            names = {p.name for p in cmd.params}
            if "cmd_fmt" not in names:
                cmd.params.append(
                    click.Option(
                        ["--format", "cmd_fmt"],
                        type=click.Choice(["json", "table"]),
                        default=None,
                        help="stdout 格式",
                    )
                )
            if "cmd_demo" not in names:
                cmd.params.append(
                    click.Option(
                        ["--demo", "cmd_demo"],
                        is_flag=True,
                        help="离线 Mock",
                    )
                )
            orig = cmd.callback
            if orig is not None and not getattr(orig, "_autodl_io", False):

                @functools.wraps(orig)
                def bound(*args: Any, **kwargs: Any) -> Any:
                    ctx = click.get_current_context()
                    cmd_fmt = kwargs.pop("cmd_fmt", None)
                    cmd_demo = kwargs.pop("cmd_demo", False)
                    if cmd_fmt:
                        ctx.obj["fmt"] = cmd_fmt
                    if cmd_demo:
                        ctx.obj["demo"] = True
                    return orig(*args, **kwargs)

                bound._autodl_io = True  # type: ignore[attr-defined]
                cmd.callback = bound
        super().add_command(cmd, name)


@click.group(cls=IoGroup)
@click.version_option(version=__version__, prog_name="autodl")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "table"]),
    default="json",
    help="stdout 格式；智能体用 json",
)
@click.option("-v", "--verbose", is_flag=True, help="DEBUG 日志")
@click.option("-q", "--quiet", is_flag=True, help="仅 WARNING 及以上")
@click.option("--demo", is_flag=True, help="离线 Mock，不访问 GPU / OpenAPI")
@click.pass_context
def cli(ctx: click.Context, fmt: str, verbose: bool, quiet: bool, demo: bool) -> None:
    """AutoDL 算力 CLI。日志走 stderr，数据走 stdout。"""
    load_env()
    setup_logger(verbose=verbose, quiet=quiet)
    ctx.ensure_object(dict)
    ctx.obj["fmt"] = fmt
    ctx.obj["demo"] = demo


@cli.group(cls=IoGroup)
def config() -> None:
    """配置"""


@config.command("check")
@click.pass_context
def config_check(ctx: click.Context) -> None:
    """检查配置（密钥脱敏）"""
    snap = config_snapshot()
    demo = bool(ctx.obj["demo"]) or bool(snap["mock"])
    log.info("config_check", extra={"cmd": "config.check", "status": "ok"})
    _done(
        ctx,
        make_envelope(
            module="config.check",
            data_source=_source(demo),
            ok=True,
            items=[snap],
        ),
        EXIT_OK,
    )


@cli.group(cls=IoGroup)
def instance() -> None:
    """AutoDL 实例"""


@instance.command("list")
@click.pass_context
def instance_list(ctx: click.Context) -> None:
    """实例列表"""
    if not _live(ctx):
        item = _demo_instance()
        log.info("instance_list", extra={"cmd": "instance.list", "instance_uuid": item["uuid"], "status": "running"})
        _done(
            ctx,
            make_envelope(module="instance.list", data_source="demo", ok=True, items=[item]),
            EXIT_OK,
        )
        return
    try:
        items = autodl_api.list_instances()
    except autodl_api.ApiError as exc:
        _fail_api(ctx, "instance.list", exc)
        return
    log.info("instance_list", extra={"cmd": "instance.list", "status": "ok"})
    _done(
        ctx,
        make_envelope(module="instance.list", data_source="live", ok=True, items=items),
        EXIT_OK,
    )


@instance.command("status")
@click.option("--uuid", "uuid_", default=None, help="实例 UUID，默认 AUTODL_INSTANCE_UUID")
@click.pass_context
def instance_status(ctx: click.Context, uuid_: str | None) -> None:
    """开关机与 SSH 端口"""
    if not _live(ctx):
        item = _demo_instance()
        log.info("instance_status", extra={"cmd": "instance.status", "instance_uuid": item["uuid"], "status": "running"})
        _done(
            ctx,
            make_envelope(module="instance.status", data_source="demo", ok=True, items=[item]),
            EXIT_OK,
        )
        return
    try:
        item = autodl_api.describe(uuid_)
    except autodl_api.ApiError as exc:
        _fail_api(ctx, "instance.status", exc)
        return
    status = str(item.get("status") or "")
    ok = status not in ("shutdown", "stopped", "closed", "")
    log.info(
        "instance_status",
        extra={"cmd": "instance.status", "instance_uuid": item.get("uuid"), "status": status},
    )
    _done(
        ctx,
        make_envelope(module="instance.status", data_source="live", ok=ok, items=[item]),
        EXIT_OK if ok else EXIT_NOT_READY,
    )


@instance.command("power-on")
@click.option("--wait", is_flag=True, help="等到可 SSH")
@click.option("--uuid", "uuid_", default=None, help="实例 UUID")
@click.pass_context
def instance_power_on(ctx: click.Context, wait: bool, uuid_: str | None) -> None:
    """有卡开机（需授权）"""
    _require_power(ctx, "instance.power-on")
    if not _live(ctx):
        item = _demo_instance()
        item["waited"] = wait
        log.info("power_on", extra={"cmd": "instance.power-on", "instance_uuid": item["uuid"], "status": "running"})
        _done(
            ctx,
            make_envelope(module="instance.power-on", data_source="demo", ok=True, items=[item]),
            EXIT_OK,
        )
        return
    try:
        item = autodl_api.power_on(uuid_, wait=wait)
    except autodl_api.ApiError as exc:
        _fail_api(ctx, "instance.power-on", exc)
        return
    log.info(
        "power_on",
        extra={"cmd": "instance.power-on", "instance_uuid": item.get("uuid"), "status": item.get("status")},
    )
    _done(
        ctx,
        make_envelope(module="instance.power-on", data_source="live", ok=True, items=[item]),
        EXIT_OK,
    )


@instance.command("power-off")
@click.option("--uuid", "uuid_", default=None, help="实例 UUID")
@click.pass_context
def instance_power_off(ctx: click.Context, uuid_: str | None) -> None:
    """关机（任务会断，需授权）"""
    _require_power(ctx, "instance.power-off")
    if not _live(ctx):
        item = _demo_instance("shutdown")
        log.info("power_off", extra={"cmd": "instance.power-off", "instance_uuid": item["uuid"], "status": "shutdown"})
        _done(
            ctx,
            make_envelope(module="instance.power-off", data_source="demo", ok=True, items=[item]),
            EXIT_OK,
        )
        return
    try:
        item = autodl_api.power_off(uuid_)
    except autodl_api.ApiError as exc:
        _fail_api(ctx, "instance.power-off", exc)
        return
    log.info("power_off", extra={"cmd": "instance.power-off", "instance_uuid": item.get("uuid"), "status": "shutdown"})
    _done(
        ctx,
        make_envelope(module="instance.power-off", data_source="live", ok=True, items=[item]),
        EXIT_OK,
    )


@cli.group(cls=IoGroup)
def wallet() -> None:
    """账户"""


@wallet.command("balance")
@click.pass_context
def wallet_balance(ctx: click.Context) -> None:
    """余额（分/1000=元）"""
    if not _live(ctx):
        item = {"assets": 1000, "accumulate": 0, "voucher_balance": 0, "yuan": 1.0}
        log.info("wallet_balance", extra={"cmd": "wallet.balance", "status": "ok"})
        _done(
            ctx,
            make_envelope(module="wallet.balance", data_source="demo", ok=True, items=[item]),
            EXIT_OK,
        )
        return
    try:
        item = autodl_api.wallet_balance()
    except autodl_api.ApiError as exc:
        _fail_api(ctx, "wallet.balance", exc)
        return
    log.info("wallet_balance", extra={"cmd": "wallet.balance", "status": "ok"})
    _done(
        ctx,
        make_envelope(module="wallet.balance", data_source="live", ok=True, items=[item]),
        EXIT_OK,
    )


@cli.group(cls=IoGroup)
def tunnel() -> None:
    """SSH 隧道"""


@tunnel.command("status")
@click.pass_context
def tunnel_status(ctx: click.Context) -> None:
    """本机 8188/8088 是否在听"""
    if not _live(ctx):
        item = {
            "comfyui": {"endpoint": comfyui_endpoint(), "listening": True},
            "llm": {"endpoint": llm_base_url(), "listening": True},
            "pid": None,
        }
        log.info("tunnel_status", extra={"cmd": "tunnel.status", "status": "ok"})
        _done(
            ctx,
            make_envelope(module="tunnel.status", data_source="demo", ok=True, items=[item]),
            EXIT_OK,
        )
        return
    item = tun.status()
    ok = bool(item.get("listening"))
    log.info("tunnel_status", extra={"cmd": "tunnel.status", "status": "ok" if ok else "down"})
    _done(
        ctx,
        make_envelope(module="tunnel.status", data_source="live", ok=ok, items=[item]),
        EXIT_OK if ok else EXIT_NOT_READY,
    )


@tunnel.command("start")
@click.pass_context
def tunnel_start(ctx: click.Context) -> None:
    """后台 SSH 转发。命令立即返回，ssh 在后台。"""
    if not _live(ctx):
        item = {
            "listening": True,
            "comfyui": comfyui_endpoint(),
            "llm": llm_base_url(),
            "spawn_hint": "background_only",
        }
        log.info("tunnel_start", extra={"cmd": "tunnel.start", "status": "ok"})
        _done(
            ctx,
            make_envelope(module="tunnel.start", data_source="demo", ok=True, items=[item]),
            EXIT_OK,
        )
        return
    try:
        item = tun.start()
    except tun.TunnelError as exc:
        log.warning("tunnel_start_fail", extra={"cmd": "tunnel.start", "status": "error"})
        _done(
            ctx,
            make_envelope(
                module="tunnel.start",
                data_source="live",
                ok=False,
                items=[],
                error=str(exc),
            ),
            exc.code,
        )
        return
    ok = bool(item.get("listening") or item.get("pid") or item.get("started"))
    log.info("tunnel_start", extra={"cmd": "tunnel.start", "status": "ok" if ok else "down"})
    _done(
        ctx,
        make_envelope(module="tunnel.start", data_source="live", ok=ok, items=[item]),
        EXIT_OK if ok else EXIT_NOT_READY,
    )


@tunnel.command("stop")
@click.pass_context
def tunnel_stop(ctx: click.Context) -> None:
    """停转发"""
    if not _live(ctx):
        log.info("tunnel_stop", extra={"cmd": "tunnel.stop", "status": "ok"})
        _done(
            ctx,
            make_envelope(
                module="tunnel.stop",
                data_source="demo",
                ok=True,
                items=[{"stopped": True}],
            ),
            EXIT_OK,
        )
        return
    item = tun.stop()
    log.info("tunnel_stop", extra={"cmd": "tunnel.stop", "status": "ok"})
    _done(
        ctx,
        make_envelope(module="tunnel.stop", data_source="live", ok=True, items=[item]),
        EXIT_OK,
    )


@cli.group(cls=IoGroup)
def compute() -> None:
    """算力探活"""


@compute.command("health")
@click.pass_context
def compute_health(ctx: click.Context) -> None:
    """ComfyUI + llama 探活"""
    if _live(ctx):
        try:
            data = orch.compute_health()
        except orch.OrchError as exc:
            _fail_orch(ctx, "compute.health", exc)
            return
        ok = bool(data.get("ok"))
        item = {**data, "orchestrator": orch_base()}
        log.info(
            "compute_health",
            extra={
                "cmd": "compute.health",
                "status": "ok" if ok else "down",
                "provider": data.get("provider"),
            },
        )
        _done(
            ctx,
            make_envelope(
                module="compute.health",
                data_source="live",
                ok=ok,
                items=[item],
            ),
            EXIT_OK if ok else EXIT_NOT_READY,
        )
        return
    item = {
        "ok": True,
        "comfyui": {"ok": True, "provider": "mock", "endpoint": comfyui_endpoint()},
        "llm": {"ok": True, "provider": "mock", "endpoint": llm_base_url()},
        "orchestrator": orch_base(),
    }
    log.info("compute_health", extra={"cmd": "compute.health", "status": "ok", "provider": "mock"})
    _done(
        ctx,
        make_envelope(module="compute.health", data_source="demo", ok=True, items=[item]),
        EXIT_OK,
    )


@cli.group(cls=IoGroup)
def job() -> None:
    """生成任务"""


def _encode_image_arg(value: str) -> str:
    text = value.strip()
    if text.startswith("data:") or text.startswith("http://") or text.startswith("https://"):
        return text
    path = Path(text).expanduser()
    if not path.is_file():
        raise VideoRequestError(f"参考图不存在: {text}")
    data = path.read_bytes()
    if not data or len(data) > 20 * 1024 * 1024:
        raise VideoRequestError("参考图为空或超过 20MB")
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(path.suffix.lower())
    if mime is None:
        raise VideoRequestError(f"不支持的参考图类型: {path.suffix or 'unknown'}")
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


@job.command("submit")
@click.option("--modality", type=click.Choice(_MODALITY), required=True)
@click.option("--prompt", required=True)
@click.option("--workflow", "workflow_id", default=None, help="留空时按 --play 选择 t2v.u03 / t2v.i2v / t2v.flf2v / t2v.r2v")
@click.option("--play", type=click.Choice(PLAY_MODES), default=None, help="text | first_frame | first_last_frame | multi")
@click.option("--image", "images", multiple=True, help="参考图路径、data URL 或 http。可重复")
@click.option("--images", "images_csv", default=None, help="多图路径，用 | 分隔。给 Agent 模板用")
@click.option("--end-image", default=None, help="首尾帧的尾帧")
@click.option("--width", type=int, default=None, help="64–4096，生效夹到 256–1344 并对齐 16。默认 768")
@click.option("--height", type=int, default=None, help="同 width。默认 768")
@click.option("--duration", type=float, default=None, help="秒，0–60。大于 0 才换算帧数，结果对齐 17k+5 且不超过 243（约 10 秒）")
@click.option("--fps", type=int, default=None, help="1–60，默认按 24 换算")
@click.option("--steps", type=int, default=None, help="1–8，默认 4")
@click.option("--seed", type=int, default=None, help="省略或 -1 为随机")
@click.option("--run-id", default=None)
@click.pass_context
def job_submit(
    ctx: click.Context,
    modality: str,
    prompt: str,
    workflow_id: str | None,
    play: str | None,
    images: tuple[str, ...],
    images_csv: str | None,
    end_image: str | None,
    width: int | None,
    height: int | None,
    duration: float | None,
    fps: int | None,
    steps: int | None,
    seed: int | None,
    run_id: str | None,
) -> None:
    """提交任务。视频可带参考图。未授权 GPU 时必须 --demo。"""
    try:
        encoded = [_encode_image_arg(item) for item in images if item and item.strip()]
        if images_csv and images_csv.strip():
            encoded.extend(_encode_image_arg(part) for part in images_csv.split("|") if part.strip())
        end_encoded = _encode_image_arg(end_image) if end_image and end_image.strip() else None
        video = resolve_video_request(
            modality=modality,
            play=play,
            images=encoded,
            end_image=end_encoded,
        )
        controls = video_controls(width=width, height=height, duration=duration, fps=fps, steps=steps, seed=seed)
    except VideoRequestError as exc:
        env = make_envelope(module="job.submit", data_source=_source(bool(ctx.obj.get("demo"))), ok=False, items=[], error=str(exc))
        log.warning("job_submit_rejected", extra={"cmd": "job.submit", "status": "rejected"})
        _done(ctx, env, EXIT_ERROR)
        return
    chosen_workflow = workflow_id or video.get("workflow_id")
    log.info(
        "job_submit",
        extra={"cmd": "job.submit", "status": video.get("play_mode") or modality, "service_id": chosen_workflow},
    )
    if _live(ctx):
        try:
            job_row = orch.create_job(
                modality=modality,
                prompt=prompt,
                workflow_id=chosen_workflow,
                run_id=run_id,
                play_mode=video.get("play_mode"),
                image_ref=video.get("image_ref"),
                end_image_ref=video.get("end_image_ref"),
                image_refs=video.get("image_refs"),
                width=controls.get("width"),
                height=controls.get("height"),
                duration=controls.get("duration"),
                fps=controls.get("fps"),
                steps=controls.get("steps"),
                seed=controls.get("seed"),
            )
        except orch.OrchError as exc:
            _fail_orch(ctx, "job.submit", exc)
            return
        _emit_job(ctx, "job.submit", job_row, "live")
        return
    job_row = create_demo_job(
        modality=modality,  # type: ignore[arg-type]
        prompt=prompt,
        workflow_id=chosen_workflow,
        run_id=run_id,
        play_mode=video.get("play_mode"),
        controls=controls,
    )
    _emit_job(ctx, "job.submit", job_row, "demo")


@job.command("get")
@click.argument("job_id")
@click.pass_context
def job_get(ctx: click.Context, job_id: str) -> None:
    """查任务"""
    if _live(ctx):
        try:
            job_row = orch.get_job(job_id)
        except orch.OrchError as exc:
            _fail_orch(ctx, "job.get", exc)
            return
        _emit_job(ctx, "job.get", job_row, "live", kind="get")
        return
    job_row = get_job(job_id)
    if job_row is None:
        env = make_envelope(module="job.get", data_source="demo", ok=False, items=[], job_id=job_id)
        log.warning("job_missing", extra={"cmd": "job.get", "job_id": job_id, "status": "missing"})
        _done(ctx, env, EXIT_NOT_READY)
        return
    _emit_job(ctx, "job.get", job_row, "demo", kind="get")


@job.command("list")
@click.option("--modality", type=click.Choice(_MODALITY), default=None)
@click.option("--limit", default=50, type=int)
@click.pass_context
def job_list(ctx: click.Context, modality: str | None, limit: int) -> None:
    """列表"""
    if _live(ctx):
        try:
            items = orch.list_jobs(modality=modality, limit=limit)
        except orch.OrchError as exc:
            _fail_orch(ctx, "job.list", exc)
            return
        data_source = "live"
    else:
        items = list_jobs(modality=modality, limit=limit)
        data_source = "demo"
    log.info("job_list", extra={"cmd": "job.list", "status": "ok"})
    _done(
        ctx,
        make_envelope(module="job.list", data_source=data_source, ok=True, items=items),
        EXIT_OK,
    )


@job.command("wait")
@click.argument("job_id")
@click.pass_context
def job_wait(ctx: click.Context, job_id: str) -> None:
    """等到终态。Demo 任务已完成，立即返回。"""
    if _live(ctx):
        try:
            job_row = orch.wait_job(job_id)
        except orch.OrchError as exc:
            _fail_orch(ctx, "job.wait", exc)
            return
        _emit_job(ctx, "job.wait", job_row, "live", kind="wait")
        return
    job_row = get_job(job_id)
    if job_row is None:
        env = make_envelope(module="job.wait", data_source="demo", ok=False, items=[], job_id=job_id)
        _done(ctx, env, EXIT_NOT_READY)
        return
    _emit_job(ctx, "job.wait", job_row, "demo", kind="wait")


@job.command("file")
@click.argument("job_id")
@click.option("-o", "--output", default=None, help="复制产物到此路径")
@click.pass_context
def job_file(ctx: click.Context, job_id: str, output: str | None) -> None:
    """拉产物"""
    dest = Path(output) if output else None
    if _live(ctx):
        try:
            job_row = orch.get_job(job_id)
            path = orch.download_file(job_id, dest)
        except orch.OrchError as exc:
            _fail_orch(ctx, "job.file", exc)
            return
        item = {"id": job_id, "path": str(path), "source": job_row.get("output_uri")}
        log.info(
            "job_file",
            extra={"cmd": "job.file", "job_id": job_id, "run_id": job_row.get("run_id"), "status": "ok"},
        )
        _done(
            ctx,
            make_envelope(
                module="job.file",
                data_source="live",
                ok=True,
                items=[item],
                run_id=job_row.get("run_id"),
                job_id=job_id,
            ),
            EXIT_OK,
        )
        return
    job_row = get_job(job_id)
    if job_row is None or not job_row.get("output_uri"):
        env = make_envelope(module="job.file", data_source="demo", ok=False, items=[], job_id=job_id)
        _done(ctx, env, EXIT_NOT_READY)
        return
    src = Path(job_row["output_uri"])
    if not src.is_file():
        env = make_envelope(module="job.file", data_source="demo", ok=False, items=[], job_id=job_id, error="artifact missing")
        _done(ctx, env, EXIT_NOT_READY)
        return
    if dest:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    item = {"id": job_id, "path": str(dest) if dest else str(src), "source": str(src)}
    log.info("job_file", extra={"cmd": "job.file", "job_id": job_id, "run_id": job_row["run_id"], "status": "ok"})
    _done(
        ctx,
        make_envelope(
            module="job.file",
            data_source="demo",
            ok=True,
            items=[item],
            run_id=job_row["run_id"],
            job_id=job_id,
        ),
        EXIT_OK,
    )


@cli.group(cls=IoGroup)
def service() -> None:
    """对外暴露的生成服务目录"""


@service.command("list")
@click.option("--exposed", is_flag=True, help="只列出已对外暴露")
@click.option("--modality", type=click.Choice(_MODALITY), default=None)
@click.pass_context
def service_list(ctx: click.Context, exposed: bool, modality: str | None) -> None:
    """列出文本 / 图片 / 视频服务。"""
    if _live(ctx):
        try:
            items = orch.list_services(exposed=True if exposed else None, modality=modality)
        except orch.OrchError as exc:
            _fail_orch(ctx, "service.list", exc)
            return
        source = "live"
    else:
        items = demo_items(exposed_only=exposed, modality=modality)
        source = "demo"
    log.info(
        "service_list",
        extra={"cmd": "service.list", "status": "ok", "modality": modality or "all"},
    )
    _done(
        ctx,
        make_envelope(module="service.list", data_source=source, ok=True, items=items),
        EXIT_OK,
    )


@cli.group(cls=IoGroup)
def llm() -> None:
    """文本模型"""


@llm.command("chat")
@click.option("--prompt", required=True)
@click.pass_context
def llm_chat(ctx: click.Context, prompt: str) -> None:
    """文本一轮"""
    if _live(ctx):
        try:
            job_row = orch.create_job(modality="text", prompt=prompt, workflow_id="llm.chat")
            path = orch.download_file(job_row["id"])
            text = path.read_text(encoding="utf-8")
        except orch.OrchError as exc:
            _fail_orch(ctx, "llm.chat", exc)
            return
        item = {**job_row, "text": text.strip()}
        log.info(
            "llm_chat",
            extra={
                "cmd": "llm.chat",
                "run_id": job_row.get("run_id"),
                "job_id": job_row.get("id"),
                "provider": job_row.get("provider"),
                "status": job_row.get("status"),
            },
        )
        ok = job_row.get("status") == "succeeded"
        _done(
            ctx,
            make_envelope(
                module="llm.chat",
                data_source="live",
                ok=ok,
                items=[item],
                run_id=job_row.get("run_id"),
                job_id=job_row.get("id"),
            ),
            EXIT_OK if ok else EXIT_COMPUTE_FAIL,
        )
        return
    job_row = create_demo_job(modality="text", prompt=prompt, workflow_id="llm.chat")
    text = Path(job_row["output_uri"]).read_text(encoding="utf-8") if job_row.get("output_uri") else ""
    item = {**job_row, "text": text.strip()}
    log.info(
        "llm_chat",
        extra={
            "cmd": "llm.chat",
            "run_id": job_row["run_id"],
            "job_id": job_row["id"],
            "provider": "mock",
            "status": "succeeded",
        },
    )
    _done(
        ctx,
        make_envelope(
            module="llm.chat",
            data_source="demo",
            ok=True,
            items=[item],
            run_id=job_row["run_id"],
            job_id=job_row["id"],
        ),
        EXIT_OK,
    )


def main() -> None:
    cli(auto_envvar_prefix="AUTODL")
