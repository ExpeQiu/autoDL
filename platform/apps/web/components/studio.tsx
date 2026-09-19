"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ImageIcon, Loader2, Sparkles, Trash2, Type, Video, X } from "lucide-react";
import { api, artifactUrl, type ComputeHealth, type Job, type JobStats, type Modality } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { SiteNav } from "@/components/site-nav";
import { cn } from "@/lib/utils";

const PRESETS: Record<Modality, { workflow: string; prompt: string; label: string }> = {
  text: {
    workflow: "llm.chat",
    label: "文本",
    prompt: "用三句话说明这个生成测试平台做什么。",
  },
  image: {
    workflow: "t2i.demo",
    label: "图片",
    prompt: "暖色实验室里一台显示器亮着，桌面有咖啡与便签，电影感。",
  },
  video: {
    workflow: "t2v.u03",
    label: "视频",
    prompt: "镜头缓缓穿过灯带走廊，尘埃在光柱里浮动，电影感。",
  },
};

function formatTime(iso: string) {
  try {
    return new Date(iso).toLocaleString("zh-CN", { hour12: false });
  } catch {
    return iso;
  }
}

function formatElapsed(ms: number | null | undefined) {
  if (ms == null || Number.isNaN(ms)) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const mins = Math.floor(ms / 60_000);
  const secs = Math.round((ms % 60_000) / 1000);
  return `${mins}m${secs}s`;
}

function formatPct(rate: number | null | undefined) {
  if (rate == null) return "—";
  return `${(rate * 100).toFixed(1)}%`;
}

const STATUS_LABEL: Record<Job["status"], string> = {
  queued: "排队",
  running: "生成中",
  succeeded: "成功",
  failed: "失败",
};

export function Studio() {
  const [modality, setModality] = useState<Modality>("image");
  const [prompt, setPrompt] = useState(PRESETS.image.prompt);
  const [filter, setFilter] = useState<Modality | "all">("all");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [stats, setStats] = useState<JobStats | null>(null);
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mock, setMock] = useState(true);
  const [mockText, setMockText] = useState(true);
  const [mockImage, setMockImage] = useState(true);
  const [compute, setCompute] = useState<ComputeHealth | null>(null);
  const [orchOk, setOrchOk] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [h, c, list, s] = await Promise.all([api.health(), api.compute(), api.jobs(filter), api.stats(filter)]);
      setOrchOk(h.ok);
      setMock(h.mock);
      setMockText(h.mock_text ?? h.mock);
      setMockImage(h.mock_image ?? h.mock);
      setCompute(c);
      setJobs(list.items);
      setStats(s);
    } catch (err) {
      setOrchOk(false);
      setError(err instanceof Error ? err.message : "编排不可达");
    }
  }, [filter]);

  const hasActive = jobs.some((j) => j.status === "queued" || j.status === "running");

  useEffect(() => {
    void refresh();
    const t = setInterval(() => void refresh(), hasActive || busy ? 2000 : 8000);
    return () => clearInterval(t);
  }, [refresh, hasActive, busy]);

  useEffect(() => {
    setPrompt(PRESETS[modality].prompt);
  }, [modality]);

  const submit = async () => {
    const text = prompt.trim();
    if (!text) return;
    setBusy(true);
    setError(null);
    try {
      await api.create({
        modality,
        prompt: text,
        workflow_id: PRESETS[modality].workflow,
      });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "提交失败");
    } finally {
      setBusy(false);
    }
  };

  const rate = async (job: Job, score: number) => {
    try {
      const updated = await api.score(job.id, score);
      setJobs((prev) => prev.map((j) => (j.id === updated.id ? updated : j)));
      setStats(await api.stats(filter));
    } catch (err) {
      setError(err instanceof Error ? err.message : "打分失败");
    }
  };

  const remove = async (job: Job) => {
    if (!window.confirm("删除这条测试结果？不可恢复。")) return;
    setError(null);
    try {
      await api.remove(job.id);
      setJobs((prev) => prev.filter((j) => j.id !== job.id));
      setPreviewId((id) => (id === job.id ? null : id));
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    }
  };

  const clearMock = async () => {
    setError(null);
    try {
      await api.clearMock();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "清理失败");
    }
  };

  const computeLabel = useMemo(() => {
    const c = compute?.comfyui;
    if (!c) return "图探测中";
    if (c.provider === "mock") return "图 Mock";
    if (c.ok) return "ComfyUI 就绪";
    return c.reason ?? "ComfyUI 断开";
  }, [compute]);

  const llmLabel = useMemo(() => {
    const l = compute?.llm;
    if (!l) return "文探测中";
    if (l.provider === "mock") return "文 Mock";
    if (l.ok) return `LLM ${l.model ?? "就绪"}`;
    return l.reason ?? "LLM 断开";
  }, [compute]);

  const previewJob = jobs.find((j) => j.id === previewId) ?? null;

  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col gap-8 px-6 py-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-xs tracking-[0.2em] text-amber-500/80">GEN TEST LAB</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">生成测试平台</h1>
          <p className="mt-1 text-sm text-stone-400">文本接 llama.cpp · 图/视频接 ComfyUI</p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <SiteNav current="studio" />
          <a href="/services" className="flex flex-wrap justify-end gap-2 text-xs" title="打开服务配置">
            <Pill ok={orchOk}>{orchOk ? "编排在线" : "编排离线"}</Pill>
            <Pill ok={compute?.llm?.ok && compute?.llm?.provider === "llamacpp"}>{llmLabel}</Pill>
            <Pill ok={compute?.comfyui?.ok}>{computeLabel}</Pill>
            <Pill ok={mockImage} warn>
              {mockImage ? "图 Mock" : "图真算力"}
            </Pill>
            <Pill ok={mock} warn>
              {mock ? "视频 Mock" : "视频真算力"}
            </Pill>
            <Pill ok={mockText} warn>
              {mockText ? "文 Mock" : "文真模型"}
            </Pill>
          </a>
        </div>
      </header>

      <section className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="rounded-xl border border-stone-800 bg-stone-900/60 p-5 shadow-[0_0_0_1px_rgba(245,158,11,0.06)]">
          <div className="mb-4 flex gap-2">
            {(Object.keys(PRESETS) as Modality[]).map((key) => {
              const Icon = key === "text" ? Type : key === "image" ? ImageIcon : Video;
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => setModality(key)}
                  className={cn(
                    "inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm",
                    modality === key
                      ? "bg-amber-500 text-stone-950"
                      : "bg-stone-800 text-stone-300 hover:bg-stone-700",
                  )}
                >
                  <Icon className="size-4" />
                  {PRESETS[key].label}
                </button>
              );
            })}
          </div>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={5}
            className="w-full resize-y rounded-md border border-stone-700 bg-stone-950/80 px-3 py-2 text-sm leading-6 text-stone-100 outline-none focus:border-amber-500/70"
            placeholder="输入提示词"
          />
          <div className="mt-3 flex items-center justify-between gap-3">
            <p className="text-xs text-stone-500">工作流 {PRESETS[modality].workflow}</p>
            <Button onClick={() => void submit()} disabled={busy || !prompt.trim()}>
              {busy ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
              {busy ? "已提交" : "生成"}
            </Button>
          </div>
          {error ? <p className="mt-3 text-sm text-red-400">{error}</p> : null}
        </div>

        <aside className="rounded-xl border border-stone-800 bg-stone-900/40 p-5 text-sm text-stone-400">
          <h2 className="mb-2 text-stone-200">怎么用</h2>
          <ol className="list-decimal space-y-2 pl-4">
            <li>文本走 Qwen3.8-27B，提交后结果墙会显示「生成中」，约十几秒到一分钟出字。</li>
            <li>视频走 MiniMax H3（隧道 :8188）。首次加载权重可能要十几分钟，结果墙会从 queued 变成 succeeded。</li>
            <li>本卡无文生图权重，图片默认 Mock。</li>
            <li>对结果点 1–5 星做验收记录；点卡片看全文或视频；右上角删除。</li>
          </ol>
        </aside>
      </section>

      <section>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-medium">结果墙</h2>
          <div className="flex items-center gap-2">
            <div className="flex gap-1 rounded-md bg-stone-900 p-1">
              {(["all", "text", "image", "video"] as const).map((key) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setFilter(key)}
                  className={cn(
                    "rounded px-2.5 py-1 text-xs",
                    filter === key ? "bg-stone-700 text-white" : "text-stone-400 hover:text-stone-200",
                  )}
                >
                  {key === "all" ? "全部" : PRESETS[key].label}
                </button>
              ))}
            </div>
            <Button type="button" variant="outline" size="sm" onClick={() => void clearMock()}>
              清理 Mock
            </Button>
          </div>
        </div>
        {stats ? <StatsPanel stats={stats} /> : null}
        {jobs.length === 0 ? (
          <p className="rounded-xl border border-dashed border-stone-800 px-4 py-16 text-center text-sm text-stone-500">
            还没有任务。提交一条提示词即可。
          </p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {jobs.map((job) => (
              <JobCard
                key={job.id}
                job={job}
                onScore={rate}
                onDelete={remove}
                onOpen={() => setPreviewId(job.id)}
              />
            ))}
          </div>
        )}
      </section>
      {previewJob ? <JobPreview job={previewJob} onClose={() => setPreviewId(null)} /> : null}
    </div>
  );
}

function Pill({
  ok,
  warn,
  children,
}: {
  ok?: boolean;
  warn?: boolean;
  children: React.ReactNode;
}) {
  const color = warn
    ? "border-amber-700 text-amber-300"
    : ok
      ? "border-emerald-800 text-emerald-300"
      : "border-red-900 text-red-300";
  return (
    <span className={cn("rounded-full border px-2.5 py-1", color)}>{children}</span>
  );
}

function StatCell({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-stone-800 bg-stone-950/50 px-3 py-2">
      <p className="text-[10px] tracking-wide text-stone-500">{label}</p>
      <p className="mt-0.5 text-sm font-medium text-stone-100">{value}</p>
      {hint ? <p className="mt-0.5 text-[10px] text-stone-600">{hint}</p> : null}
    </div>
  );
}

const SCORE_BAR: Record<1 | 2 | 3 | 4 | 5, string> = {
  1: "bg-stone-500",
  2: "bg-amber-800",
  3: "bg-amber-600",
  4: "bg-amber-500",
  5: "bg-amber-400",
};

function ScoreDist({ stats }: { stats: JobStats }) {
  const scored = stats.scored_count;
  return (
    <div className="mt-3 rounded-lg border border-stone-800 bg-stone-950/40 px-3 py-3">
      <div className="mb-2.5 flex items-baseline justify-between gap-3">
        <p className="text-xs font-medium text-stone-300">评分分布</p>
        <p className="text-[11px] text-stone-500">
          {scored ? `已评 ${scored} / ${stats.total}` : "尚无评分"}
        </p>
      </div>
      {scored === 0 ? (
        <p className="rounded-md bg-stone-900/80 px-3 py-4 text-center text-[11px] text-stone-600">
          对结果点 1–5 星后，这里会按星级汇总占比
        </p>
      ) : (
        <>
          <div className="mb-3 flex h-2 overflow-hidden rounded-full bg-stone-800">
            {([1, 2, 3, 4, 5] as const).map((n) => {
              const count = stats.score_hist[String(n)] ?? 0;
              if (!count) return null;
              return (
                <div
                  key={n}
                  className={cn("h-full", SCORE_BAR[n])}
                  style={{ width: `${(count / scored) * 100}%` }}
                  title={`${n} 星 ${count} 条`}
                />
              );
            })}
          </div>
          <div className="space-y-1.5">
            {([1, 2, 3, 4, 5] as const).map((n) => {
              const count = stats.score_hist[String(n)] ?? 0;
              const pct = (count / scored) * 100;
              return (
                <div
                  key={n}
                  className="grid grid-cols-[2.75rem_minmax(0,1fr)_4.75rem] items-center gap-2 text-[11px]"
                >
                  <span className="tabular-nums text-stone-400">{n} 星</span>
                  <div className="h-1.5 overflow-hidden rounded-full bg-stone-800">
                    <div
                      className={cn("h-full rounded-full transition-[width]", SCORE_BAR[n], count ? "" : "opacity-0")}
                      style={{ width: `${Math.max(count ? 4 : 0, pct)}%` }}
                    />
                  </div>
                  <span className="text-right tabular-nums text-stone-500">
                    {count}
                    <span className="ml-1.5 text-stone-600">{pct.toFixed(0)}%</span>
                  </span>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

function StatsPanel({ stats }: { stats: JobStats }) {
  const modalityHint = (["text", "image", "video"] as const)
    .map((k) => {
      const n = stats.by_modality[k];
      if (!n) return null;
      return `${PRESETS[k].label} ${n}`;
    })
    .filter(Boolean)
    .join(" · ");
  return (
    <div className="mb-4 rounded-xl border border-stone-800 bg-stone-900/50 p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="text-sm font-medium text-stone-200">评测统计</h3>
        <p className="text-[11px] text-stone-500">{modalityHint || "当前筛选无任务"}</p>
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8">
        <StatCell label="任务数" value={String(stats.total)} />
        <StatCell label="成功" value={String(stats.by_status.succeeded ?? 0)} />
        <StatCell label="失败" value={String(stats.by_status.failed ?? 0)} />
        <StatCell
          label="进行中"
          value={String((stats.by_status.queued ?? 0) + (stats.by_status.running ?? 0))}
        />
        <StatCell label="成功率" value={formatPct(stats.success_rate)} />
        <StatCell
          label="平均耗时"
          value={formatElapsed(stats.avg_elapsed_ms)}
          hint={stats.p95_elapsed_ms != null ? `P95 ${formatElapsed(stats.p95_elapsed_ms)}` : undefined}
        />
        <StatCell
          label="平均分"
          value={stats.avg_score == null ? "—" : stats.avg_score.toFixed(2)}
          hint={`已评 ${stats.scored_count}`}
        />
        <StatCell
          label="平均 Token"
          value={
            stats.avg_completion_tokens == null
              ? "—"
              : `${Math.round(stats.avg_prompt_tokens ?? 0)}→${Math.round(stats.avg_completion_tokens)}`
          }
        />
      </div>
      <ScoreDist stats={stats} />
    </div>
  );
}

function JobCard({
  job,
  onScore,
  onDelete,
  onOpen,
}: {
  job: Job;
  onScore: (job: Job, score: number) => void;
  onDelete: (job: Job) => void;
  onOpen: () => void;
}) {
  const [text, setText] = useState<string | null>(null);
  const src = artifactUrl(job);
  const statusColor =
    job.status === "succeeded"
      ? "text-emerald-400"
      : job.status === "failed"
        ? "text-red-400"
        : "text-amber-400";
  const isVideo = job.modality === "video" && Boolean(src) && !job.output_uri?.endsWith(".txt");

  useEffect(() => {
    if (job.modality === "text" && src) {
      void api.text(job).then(setText).catch(() => setText(job.prompt));
    }
  }, [job, src]);

  return (
    <article
      className="cursor-pointer overflow-hidden rounded-xl border border-stone-800 bg-stone-900/70 transition-colors hover:border-stone-600"
      onClick={onOpen}
    >
      <div className="relative aspect-[3/2] bg-stone-950">
        {job.status === "queued" || job.status === "running" ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-amber-400/80">
            <Loader2 className="size-8 animate-spin" />
            <span className="text-xs">{job.status === "queued" ? "排队中" : "生成中"}</span>
          </div>
        ) : job.status === "failed" ? (
          <div className="flex h-full items-center p-4 text-xs leading-5 text-red-400">
            {job.error || "生成失败"}
          </div>
        ) : job.modality === "image" && src ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={src} alt={job.prompt} className="h-full w-full object-cover" />
        ) : isVideo ? (
          <>
            <video src={src ?? undefined} muted playsInline className="h-full w-full object-cover" />
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-black/20">
              <span className="rounded-full bg-stone-950/80 px-3 py-1 text-[11px] text-stone-200">点击播放</span>
            </div>
          </>
        ) : job.modality === "video" ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-stone-500">
            <Video className="size-8" />
            <span className="text-xs">Mock 视频占位</span>
          </div>
        ) : (
          <pre className="h-full overflow-hidden p-3 text-xs leading-5 text-stone-300 whitespace-pre-wrap">
            {text ?? "读取中…"}
          </pre>
        )}
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onDelete(job);
          }}
          className="absolute right-2 top-2 inline-flex size-8 items-center justify-center rounded-md border border-stone-700/80 bg-stone-950/80 text-stone-300 hover:border-red-800 hover:text-red-300"
          aria-label="删除"
          title="删除"
        >
          <Trash2 className="size-4" />
        </button>
      </div>
      <div className="space-y-2 p-3">
        <p className="line-clamp-2 text-sm text-stone-200">{job.prompt}</p>
        <p className="text-[11px] text-stone-500">
          <span className={statusColor}>{STATUS_LABEL[job.status]}</span>
          {" · "}
          {job.model || job.provider}
          {" · "}
          {formatElapsed(job.elapsed_ms)}
          {job.prompt_tokens != null && job.completion_tokens != null
            ? ` · ${job.prompt_tokens}→${job.completion_tokens} tok`
            : job.output_chars != null
              ? ` · ${job.output_chars} 字`
              : ""}
        </p>
        <p className="text-[11px] text-stone-600">{formatTime(job.created_at)}</p>
        <div className="flex gap-1">
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onScore(job, n);
              }}
              className={cn(
                "size-7 rounded text-xs",
                job.score && job.score >= n ? "bg-amber-500 text-stone-950" : "bg-stone-800 text-stone-400",
              )}
            >
              {n}
            </button>
          ))}
        </div>
      </div>
    </article>
  );
}

function JobPreview({ job, onClose }: { job: Job; onClose: () => void }) {
  const [text, setText] = useState<string | null>(null);
  const src = artifactUrl(job);
  const isVideo = job.modality === "video" && Boolean(src) && !job.output_uri?.endsWith(".txt");

  useEffect(() => {
    if (job.modality === "text" && src) {
      void api.text(job).then(setText).catch(() => setText(job.prompt));
    }
  }, [job, src]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-8" role="dialog" aria-modal="true">
      <button type="button" className="absolute inset-0 bg-black/75" onClick={onClose} aria-label="关闭" />
      <div className="relative z-10 flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-xl border border-stone-700 bg-stone-950 shadow-2xl">
        <div className="flex items-start justify-between gap-3 border-b border-stone-800 px-4 py-3">
          <div className="min-w-0">
            <p className="text-sm text-stone-200">{job.prompt}</p>
            <p className="mt-1 text-[11px] text-stone-500">
              {STATUS_LABEL[job.status]} · {job.model || job.provider} · {formatElapsed(job.elapsed_ms)}
              {job.prompt_tokens != null && job.completion_tokens != null
                ? ` · ${job.prompt_tokens}→${job.completion_tokens} tok`
                : ""}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex size-8 shrink-0 items-center justify-center rounded-md text-stone-400 hover:bg-stone-800 hover:text-stone-100"
            aria-label="关闭"
          >
            <X className="size-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto bg-stone-950">
          {job.status === "queued" || job.status === "running" ? (
            <div className="flex h-64 flex-col items-center justify-center gap-2 text-amber-400/80">
              <Loader2 className="size-8 animate-spin" />
              <span className="text-xs">{job.status === "queued" ? "排队中" : "生成中"}</span>
            </div>
          ) : job.status === "failed" ? (
            <p className="p-6 text-sm leading-6 text-red-400">{job.error || "生成失败"}</p>
          ) : job.modality === "image" && src ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={src} alt={job.prompt} className="mx-auto max-h-[72vh] w-auto object-contain" />
          ) : isVideo ? (
            <video src={src ?? undefined} controls autoPlay className="max-h-[72vh] w-full bg-black" />
          ) : job.modality === "video" ? (
            <div className="flex h-64 flex-col items-center justify-center gap-2 text-stone-500">
              <Video className="size-8" />
              <span className="text-sm">Mock 视频占位，无真实画面</span>
            </div>
          ) : (
            <pre className="whitespace-pre-wrap p-5 text-sm leading-7 text-stone-200">{text ?? "读取中…"}</pre>
          )}
        </div>
      </div>
    </div>
  );
}
