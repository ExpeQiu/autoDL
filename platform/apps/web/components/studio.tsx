"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ImageIcon, Loader2, Sparkles, Type, Video } from "lucide-react";
import { api, artifactUrl, type ComputeHealth, type Job, type Modality } from "@/lib/api";
import { Button } from "@/components/ui/button";
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

export function Studio() {
  const [modality, setModality] = useState<Modality>("image");
  const [prompt, setPrompt] = useState(PRESETS.image.prompt);
  const [filter, setFilter] = useState<Modality | "all">("all");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mock, setMock] = useState(true);
  const [mockText, setMockText] = useState(true);
  const [mockImage, setMockImage] = useState(true);
  const [compute, setCompute] = useState<ComputeHealth | null>(null);
  const [orchOk, setOrchOk] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [h, c, list] = await Promise.all([api.health(), api.compute(), api.jobs(filter)]);
      setOrchOk(h.ok);
      setMock(h.mock);
      setMockText(h.mock_text ?? h.mock);
      setMockImage(h.mock_image ?? h.mock);
      setCompute(c);
      setJobs(list.items);
    } catch (err) {
      setOrchOk(false);
      setError(err instanceof Error ? err.message : "编排不可达");
    }
  }, [filter]);

  useEffect(() => {
    void refresh();
    const t = setInterval(() => void refresh(), 8000);
    return () => clearInterval(t);
  }, [refresh]);

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
    } catch (err) {
      setError(err instanceof Error ? err.message : "打分失败");
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

  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col gap-8 px-6 py-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-xs tracking-[0.2em] text-amber-500/80">GEN TEST LAB</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">生成测试平台</h1>
          <p className="mt-1 text-sm text-stone-400">文本接 llama.cpp · 图/视频接 ComfyUI</p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
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
            <li>视频走 MiniMax H3（隧道 :8188）。首次加载权重可能要十几分钟，结果墙会从 queued 变成 succeeded。</li>
            <li>本卡无文生图权重，图片默认 Mock。</li>
            <li>对结果点 1–5 星做验收记录。</li>
          </ol>
        </aside>
      </section>

      <section>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-medium">结果墙</h2>
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
        </div>
        {jobs.length === 0 ? (
          <p className="rounded-xl border border-dashed border-stone-800 px-4 py-16 text-center text-sm text-stone-500">
            还没有任务。提交一条提示词即可。
          </p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {jobs.map((job) => (
              <JobCard key={job.id} job={job} onScore={rate} />
            ))}
          </div>
        )}
      </section>
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

function JobCard({ job, onScore }: { job: Job; onScore: (job: Job, score: number) => void }) {
  const [text, setText] = useState<string | null>(null);
  const src = artifactUrl(job);

  useEffect(() => {
    if (job.modality === "text" && src) {
      void api.text(job).then(setText).catch(() => setText(job.prompt));
    }
  }, [job, src]);

  return (
    <article className="overflow-hidden rounded-xl border border-stone-800 bg-stone-900/70">
      <div className="aspect-[3/2] bg-stone-950">
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
        ) : job.modality === "video" && src && !job.output_uri?.endsWith(".txt") ? (
          <video src={src} controls className="h-full w-full object-cover" />
        ) : job.modality === "video" ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-stone-500">
            <Video className="size-8" />
            <span className="text-xs">Mock 视频占位</span>
          </div>
        ) : (
          <pre className="h-full overflow-auto p-3 text-xs leading-5 text-stone-300 whitespace-pre-wrap">
            {text ?? "读取中…"}
          </pre>
        )}
      </div>
      <div className="space-y-2 p-3">
        <p className="line-clamp-2 text-sm text-stone-200">{job.prompt}</p>
        <p className="text-[11px] text-stone-500">
          {job.status} · {job.provider} · {formatTime(job.created_at)}
        </p>
        <div className="flex gap-1">
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              type="button"
              onClick={() => onScore(job, n)}
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
