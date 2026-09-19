"use client";

import { useCallback, useEffect, useState } from "react";
import { ImageIcon, KeyRound, Loader2, Type, Video } from "lucide-react";
import {
  api,
  type AccessConfig,
  type AccessProfile,
  type ComputeHealth,
  type ExposedService,
  type Modality,
  type ModalityLane,
} from "@/lib/api";
import { AccessSetupDialog, SshFields } from "@/components/access-setup";
import { Button } from "@/components/ui/button";
import { SiteNav } from "@/components/site-nav";
import { cn } from "@/lib/utils";

const MODALITY_META: Record<Modality, { label: string; Icon: typeof Type }> = {
  text: { label: "文本", Icon: Type },
  image: { label: "图片", Icon: ImageIcon },
  video: { label: "视频", Icon: Video },
};

function defaultLane(mod: Modality, profile: AccessProfile): ModalityLane {
  if (mod === "text") {
    return {
      enabled: true,
      mock: false,
      endpoint: "http://127.0.0.1:8088",
      model: profile === "autodl" ? "qwen3.8-27b" : "qwen3-8b",
      tunnel_local: 8088,
      tunnel_remote: 8088,
    };
  }
  return {
    enabled: true,
    mock: false,
    endpoint: "http://127.0.0.1:8188",
    model: mod === "image" ? "t2i.demo" : "t2v.u03",
    tunnel_local: 8188,
    tunnel_remote: 8188,
  };
}

function mergeLane(raw: ModalityLane | undefined, fallback: ModalityLane): ModalityLane {
  if (!raw || typeof raw !== "object") return fallback;
  return { ...fallback, ...raw };
}

function laneKey(profile: AccessProfile, mod: Modality): `${AccessProfile}_${Modality}` {
  return `${profile}_${mod}`;
}

const EMPTY_ACCESS: AccessConfig = {
  profile: "autodl",
  mock_text: false,
  mock_image: false,
  mock_video: false,
  comfyui_endpoint: "http://127.0.0.1:8188",
  llm_base_url: "http://127.0.0.1:8088",
  llm_model: "qwen3-8b",
  local_comfyui_endpoint: "http://127.0.0.1:8188",
  local_llm_base_url: "http://127.0.0.1:8088",
  local_llm_model: "qwen3-8b",
  autodl_comfyui_endpoint: "http://127.0.0.1:8188",
  autodl_llm_base_url: "http://127.0.0.1:8088",
  autodl_llm_model: "qwen3.8-27b",
  autodl_ssh_host: "",
  autodl_ssh_port: 0,
  autodl_ssh_user: "root",
  autodl_ssh_auth: "password",
  autodl_ssh_key_path: "",
  autodl_ssh_password_set: false,
  local_text: defaultLane("text", "local"),
  local_image: defaultLane("image", "local"),
  local_video: defaultLane("video", "local"),
  autodl_text: defaultLane("text", "autodl"),
  autodl_image: defaultLane("image", "autodl"),
  autodl_video: defaultLane("video", "autodl"),
};

const PROFILES: { id: AccessProfile; title: string; desc: string }[] = [
  { id: "local", title: "本地服务", desc: "本机或局域网 GPU" },
  { id: "autodl", title: "autodl租赁", desc: "SSH 隧道后的实例" },
];

const ORCH_LANES: {
  mod: Modality;
  mockKey: "mock_text" | "mock_image" | "mock_video";
  label: string;
  modelLabel: string;
  placeholder: string;
}[] = [
  { mod: "text", mockKey: "mock_text", label: "文", modelLabel: "模型", placeholder: "qwen3.8-27b" },
  { mod: "image", mockKey: "mock_image", label: "图", modelLabel: "工作流", placeholder: "t2i.demo" },
  { mod: "video", mockKey: "mock_video", label: "视频", modelLabel: "工作流", placeholder: "t2v.u03" },
];

function synthesizeLane(acc: Partial<AccessConfig>, profile: AccessProfile, mod: Modality): ModalityLane {
  const nested = acc[laneKey(profile, mod)];
  const fallback = defaultLane(mod, profile);
  const mock = mod === "text" ? Boolean(acc.mock_text) : mod === "image" ? Boolean(acc.mock_image) : Boolean(acc.mock_video);
  const endpoint =
    mod === "text"
      ? (profile === "local" ? acc.local_llm_base_url : acc.autodl_llm_base_url) || fallback.endpoint
      : (profile === "local" ? acc.local_comfyui_endpoint : acc.autodl_comfyui_endpoint) || fallback.endpoint;
  const model =
    mod === "text"
      ? (profile === "local" ? acc.local_llm_model : acc.autodl_llm_model) || fallback.model
      : fallback.model;
  return mergeLane(nested, { ...fallback, mock, endpoint, model });
}

function fromApi(acc: AccessConfig): AccessConfig {
  return {
    ...EMPTY_ACCESS,
    ...acc,
    profile: acc.profile ?? "autodl",
    local_comfyui_endpoint: acc.local_comfyui_endpoint ?? acc.comfyui_endpoint,
    local_llm_base_url: acc.local_llm_base_url ?? acc.llm_base_url,
    local_llm_model: acc.local_llm_model ?? acc.llm_model,
    autodl_comfyui_endpoint: acc.autodl_comfyui_endpoint ?? acc.comfyui_endpoint,
    autodl_llm_base_url: acc.autodl_llm_base_url ?? acc.llm_base_url,
    autodl_llm_model: acc.autodl_llm_model ?? acc.llm_model,
    autodl_ssh_host: acc.autodl_ssh_host ?? "",
    autodl_ssh_port: acc.autodl_ssh_port ?? 0,
    autodl_ssh_user: acc.autodl_ssh_user ?? "root",
    autodl_ssh_auth: acc.autodl_ssh_auth ?? "password",
    autodl_ssh_key_path: acc.autodl_ssh_key_path ?? "",
    autodl_ssh_password_set: Boolean(acc.autodl_ssh_password_set),
    local_text: synthesizeLane(acc, "local", "text"),
    local_image: synthesizeLane(acc, "local", "image"),
    local_video: synthesizeLane(acc, "local", "video"),
    autodl_text: synthesizeLane(acc, "autodl", "text"),
    autodl_image: synthesizeLane(acc, "autodl", "image"),
    autodl_video: synthesizeLane(acc, "autodl", "video"),
  };
}

function sortServices(items: ExposedService[]) {
  const order: Modality[] = ["text", "image", "video"];
  return [...items].sort((a, b) => {
    const diff = order.indexOf(a.modality) - order.indexOf(b.modality);
    if (diff !== 0) return diff;
    return a.id.localeCompare(b.id);
  });
}

function Toggle({
  on,
  disabled,
  onClick,
}: {
  on: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-50",
        on ? "bg-amber-500" : "bg-stone-700",
      )}
    >
      <span
        className={cn(
          "absolute top-0.5 size-5 rounded-full bg-white transition-[left]",
          on ? "left-5" : "left-0.5",
        )}
      />
    </button>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="text-xs text-stone-500">
      {label}
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="mt-1 w-full rounded-md border border-stone-700 bg-stone-950/80 px-3 py-2 text-sm text-stone-100 outline-none focus:border-amber-500/70"
      />
    </label>
  );
}

export function ServicesPanel() {
  const [items, setItems] = useState<ExposedService[]>([]);
  const [access, setAccess] = useState<AccessConfig>(EMPTY_ACCESS);
  const [compute, setCompute] = useState<ComputeHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savingAccess, setSavingAccess] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [accessDirty, setAccessDirty] = useState(false);
  const [orchOk, setOrchOk] = useState(false);
  const [setupOpen, setSetupOpen] = useState(false);
  const [sshOpen, setSshOpen] = useState(false);
  const [sshPassword, setSshPassword] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [h, list, acc, c] = await Promise.all([
        api.health(),
        api.services(),
        api.access(),
        api.compute(),
      ]);
      setOrchOk(h.ok);
      setItems(sortServices(list.items));
      setAccess(fromApi(acc));
      setCompute(c);
      setDirty(false);
      setAccessDirty(false);
      setError(null);
    } catch (err) {
      setOrchOk(false);
      setError(err instanceof Error ? err.message : "编排不可达");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const patchExposed = async (id: string, exposed: boolean) => {
    setBusyId(id);
    setError(null);
    try {
      const res = await api.patchService(id, { exposed });
      setItems(sortServices(res.items));
      setDirty(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setBusyId(null);
    }
  };

  const updateLocal = (id: string, patch: Partial<ExposedService>) => {
    setItems((prev) => prev.map((item) => (item.id === id ? { ...item, ...patch } : item)));
    setDirty(true);
  };

  const patchAccess = (partial: Partial<AccessConfig>) => {
    setAccess((prev) => ({ ...prev, ...partial }));
    setAccessDirty(true);
  };

  const patchLane = (profile: AccessProfile, mod: Modality, partial: Partial<ModalityLane>) => {
    setAccess((prev) => {
      const key = laneKey(profile, mod);
      const lane = { ...prev[key], ...partial };
      const next: AccessConfig = { ...prev, [key]: lane };
      if (mod === "text") {
        if (profile === "local") {
          if (partial.endpoint !== undefined) next.local_llm_base_url = partial.endpoint;
          if (partial.model !== undefined) next.local_llm_model = partial.model;
        } else {
          if (partial.endpoint !== undefined) next.autodl_llm_base_url = partial.endpoint;
          if (partial.model !== undefined) next.autodl_llm_model = partial.model;
        }
        if (profile === prev.profile && partial.mock !== undefined) next.mock_text = partial.mock;
        if (profile === prev.profile && partial.model !== undefined) next.llm_model = partial.model;
      } else {
        if (partial.endpoint !== undefined) {
          if (profile === "local") next.local_comfyui_endpoint = partial.endpoint;
          else next.autodl_comfyui_endpoint = partial.endpoint;
        }
        if (profile === prev.profile && partial.mock !== undefined) {
          if (mod === "image") next.mock_image = partial.mock;
          else next.mock_video = partial.mock;
        }
      }
      return next;
    });
    setAccessDirty(true);
  };

  const patchActiveMock = (mod: Modality, mock: boolean) => {
    patchLane(access.profile, mod, { mock, enabled: true });
  };

  const patchActiveModel = (mod: Modality, model: string) => {
    patchLane(access.profile, mod, { model });
  };

  const saveAll = async () => {
    setSaving(true);
    setError(null);
    try {
      const res = await api.saveServices(items.map(({ invoke: _invoke, ...rest }) => rest));
      setItems(sortServices(res.items));
      setDirty(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const saveAccess = async () => {
    setSavingAccess(true);
    setError(null);
    try {
      const payload: Parameters<typeof api.saveAccess>[0] = {
        profile: access.profile,
        mock_text: access.mock_text,
        mock_image: access.mock_image,
        mock_video: access.mock_video,
        local_comfyui_endpoint: access.local_comfyui_endpoint.trim(),
        local_llm_base_url: access.local_llm_base_url.trim(),
        local_llm_model: access.local_llm_model.trim(),
        autodl_comfyui_endpoint: access.autodl_comfyui_endpoint.trim(),
        autodl_llm_base_url: access.autodl_llm_base_url.trim(),
        autodl_llm_model: access.autodl_llm_model.trim(),
        autodl_ssh_host: access.autodl_ssh_host.trim(),
        autodl_ssh_port: access.autodl_ssh_port,
        autodl_ssh_user: access.autodl_ssh_user.trim() || "root",
        autodl_ssh_auth: access.autodl_ssh_auth,
        autodl_ssh_key_path: access.autodl_ssh_key_path.trim(),
        local_text: { ...access.local_text, endpoint: access.local_text.endpoint.trim(), model: access.local_text.model.trim() },
        local_image: { ...access.local_image, endpoint: access.local_image.endpoint.trim(), model: access.local_image.model.trim() },
        local_video: { ...access.local_video, endpoint: access.local_video.endpoint.trim(), model: access.local_video.model.trim() },
        autodl_text: { ...access.autodl_text, endpoint: access.autodl_text.endpoint.trim(), model: access.autodl_text.model.trim() },
        autodl_image: { ...access.autodl_image, endpoint: access.autodl_image.endpoint.trim(), model: access.autodl_image.model.trim() },
        autodl_video: { ...access.autodl_video, endpoint: access.autodl_video.endpoint.trim(), model: access.autodl_video.model.trim() },
      };
      if (sshPassword.trim()) payload.autodl_ssh_password = sshPassword.trim();
      const saved = await api.saveAccess(payload);
      setAccess(fromApi(saved));
      setSshPassword("");
      setAccessDirty(false);
      setSetupOpen(false);
      setSshOpen(false);
      const [h, c] = await Promise.all([api.health(), api.compute()]);
      setOrchOk(h.ok);
      setCompute(c);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存接入失败");
    } finally {
      setSavingAccess(false);
    }
  };

  const exposedCount = items.filter((item) => item.exposed).length;
  const llmOk = Boolean(compute?.llm?.ok && compute?.llm?.provider === "llamacpp");
  const comfyOk = Boolean(compute?.comfyui?.ok && compute?.comfyui?.provider !== "mock");

  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col gap-8 px-6 py-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-xs tracking-[0.2em] text-amber-500/80">GEN TEST LAB</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">服务配置</h1>
          <p className="mt-1 text-sm text-stone-400">
            接入编排 / LLM / ComfyUI，并配置对外目录。测试页面上的状态标签会跳到本页。
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <SiteNav current="services" />
          <span
            className={cn(
              "rounded-full border px-2.5 py-1 text-xs",
              orchOk ? "border-emerald-800 text-emerald-300" : "border-red-900 text-red-300",
            )}
          >
            {orchOk ? "编排在线" : "编排离线"}
          </span>
        </div>
      </header>

      {error ? <p className="text-sm text-red-400">{error}</p> : null}

      <section id="access" className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-medium">服务接入</h2>
            <p className="mt-1 text-sm text-stone-400">编排定义 Mock 与模型；本地 / 租赁只配地址与 SSH，随当前路径联动。</p>
          </div>
          <div className="flex items-center gap-2">
            {accessDirty ? (
              <Button type="button" size="sm" onClick={() => void saveAccess()} disabled={savingAccess}>
                {savingAccess ? <Loader2 className="size-4 animate-spin" /> : null}
                {savingAccess ? "保存中" : "保存接入"}
              </Button>
            ) : null}
            <Button type="button" variant="outline" size="sm" onClick={() => setSetupOpen(true)}>
              配置
            </Button>
          </div>
        </div>

        <div className="flex w-fit gap-1 rounded-md bg-stone-900 p-1 text-sm">
          {PROFILES.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => patchAccess({ profile: item.id })}
              className={cn(
                "rounded px-3 py-1.5",
                access.profile === item.id ? "bg-stone-700 text-white" : "text-stone-400 hover:text-stone-200",
              )}
            >
              {item.title}
            </button>
          ))}
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <article className="flex flex-col gap-3 rounded-xl border border-stone-800 bg-stone-900/60 p-5">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-sm font-medium">编排</h3>
              <span className={cn("text-xs", orchOk ? "text-emerald-300" : "text-red-300")}>
                {orchOk ? "在线" : "离线"}
              </span>
            </div>
            <p className="font-mono text-xs text-stone-500">
              {access.orch_host ?? "127.0.0.1"}:{access.orch_port ?? 8090}
            </p>
            <p className="text-xs text-stone-500">
              当前走
              <span className="text-amber-300/90"> {access.profile === "local" ? "本地服务" : "autodl租赁"} </span>
              的 Mock 与模型。
            </p>
            {ORCH_LANES.map((item) => {
              const lane = access[laneKey(access.profile, item.mod)];
              const mocked = lane.mock || !lane.enabled;
              return (
                <div key={item.mod} className="rounded-lg border border-stone-800/80 px-3 py-2">
                  <div className="flex items-center justify-between gap-2 text-sm text-stone-300">
                    <span>{item.label} Mock</span>
                    <Toggle on={mocked} onClick={() => patchActiveMock(item.mod, !mocked)} />
                  </div>
                  <label className="mt-2 block text-xs text-stone-500">
                    {item.modelLabel}
                    <input
                      value={lane.model}
                      onChange={(e) => patchActiveModel(item.mod, e.target.value)}
                      placeholder={item.placeholder}
                      className="mt-1 w-full rounded-md border border-stone-700 bg-stone-950/80 px-3 py-2 text-sm text-stone-100 outline-none focus:border-amber-500/70"
                    />
                  </label>
                </div>
              );
            })}
          </article>

          {PROFILES.map((item) => {
            const active = access.profile === item.id;
            const textLane = access[laneKey(item.id, "text")];
            const imageLane = access[laneKey(item.id, "image")];
            const videoLane = access[laneKey(item.id, "video")];
            const llm = textLane.endpoint;
            const comfy = imageLane.enabled ? imageLane.endpoint : videoLane.endpoint;
            const textMock = textLane.mock || !textLane.enabled;
            const visionMock = (imageLane.mock || !imageLane.enabled) && (videoLane.mock || !videoLane.enabled);
            return (
              <article
                key={item.id}
                className={cn(
                  "relative flex flex-col gap-3 rounded-xl border bg-stone-900/60 p-5",
                  active ? "border-amber-700/80" : "border-stone-800",
                  item.id === "autodl" && sshOpen ? "z-20" : "",
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="text-sm font-medium">{item.title}</h3>
                    <p className="mt-0.5 text-xs text-stone-500">{item.desc}</p>
                  </div>
                  <div className="relative flex items-center gap-2">
                    {item.id === "autodl" ? (
                      <button
                        type="button"
                        onClick={() => setSshOpen((open) => !open)}
                        className={cn(
                          "inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px]",
                          sshOpen || access.autodl_ssh_port
                            ? "border-amber-800/80 text-amber-200"
                            : "border-stone-700 text-stone-400 hover:text-stone-200",
                        )}
                      >
                        <KeyRound className="size-3" />
                        {access.autodl_ssh_port ? `SSH :${access.autodl_ssh_port}` : "SSH"}
                      </button>
                    ) : null}
                    <span className={cn("text-xs", active ? "text-amber-300" : "text-stone-500")}>
                      {active ? "当前" : "备用"}
                    </span>
                    {item.id === "autodl" && sshOpen ? (
                      <div className="absolute right-0 top-8 z-20 w-72 rounded-lg border border-stone-700 bg-stone-950 p-3 shadow-xl">
                        <p className="mb-2 text-xs text-stone-400">SSH 通道及密钥</p>
                        <SshFields access={access} password={sshPassword} onPatch={patchAccess} onPassword={setSshPassword} />
                        <Button
                          type="button"
                          size="sm"
                          className="mt-3 w-full"
                          onClick={() => void saveAccess()}
                          disabled={savingAccess}
                        >
                          {savingAccess ? <Loader2 className="size-4 animate-spin" /> : null}
                          保存 SSH
                        </Button>
                      </div>
                    ) : null}
                  </div>
                </div>
                {active ? (
                  <p className={cn("text-xs", textMock ? "text-amber-300" : llmOk ? "text-emerald-300" : "text-red-300")}>
                    {textMock ? `文 Mock · ${textLane.model || "—"}` : llmOk ? `${textLane.model || "文真模型"} 就绪` : `${textLane.model || "LLM"} 断开`}
                    {" · "}
                    {comfyOk ? "ComfyUI 就绪" : visionMock ? "图/视频 Mock" : "ComfyUI 断开"}
                  </p>
                ) : (
                  <p className="text-xs text-stone-500">切到此项后，左侧编排的 Mock / 模型跟这套地址联动。</p>
                )}
                <Field
                  label="LLM 地址"
                  value={llm}
                  onChange={(v) => patchLane(item.id, "text", { endpoint: v })}
                  placeholder="http://127.0.0.1:8088"
                />
                <Field
                  label="ComfyUI 地址"
                  value={comfy}
                  onChange={(v) => {
                    patchLane(item.id, "image", { endpoint: v });
                    patchLane(item.id, "video", { endpoint: v });
                  }}
                  placeholder="http://127.0.0.1:8188"
                />
              </article>
            );
          })}
        </div>
      </section>

      <section className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-medium">对外目录</h2>
            <p className="mt-1 text-sm text-stone-400">
              已打开 <span className="text-stone-200">{exposedCount}</span> / {items.length}。cyberspaceAI 用{" "}
              <code className="text-stone-300">autodl service list</code> 发现。
            </p>
          </div>
          <Button type="button" variant="outline" size="sm" onClick={() => void saveAll()} disabled={saving || !dirty || items.some((item) => !item.label.trim())}>
            {saving ? <Loader2 className="size-4 animate-spin" /> : null}
            {saving ? "保存中" : dirty ? "保存说明" : "已保存"}
          </Button>
        </div>

        {items.length === 0 && !error ? (
          <p className="rounded-xl border border-dashed border-stone-800 px-4 py-16 text-center text-sm text-stone-500">
            正在读取服务目录…
          </p>
        ) : (
          <div className="grid gap-4 md:grid-cols-3">
            {items.map((item) => {
              const meta = MODALITY_META[item.modality];
              const Icon = meta.Icon;
              return (
                <article
                  key={item.id}
                  className="flex flex-col gap-4 rounded-xl border border-stone-800 bg-stone-900/60 p-5"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="flex items-center gap-2 text-sm text-stone-300">
                        <Icon className="size-4 text-amber-400" />
                        {meta.label}
                      </p>
                      <h3 className="mt-1 text-lg font-medium">{item.label}</h3>
                      <p className="mt-1 font-mono text-xs text-stone-500">
                        {item.id} · {item.workflow_id} · {item.provider}
                      </p>
                    </div>
                    <Toggle
                      on={item.exposed}
                      disabled={busyId === item.id}
                      onClick={() => void patchExposed(item.id, !item.exposed)}
                    />
                  </div>
                  <Field label="对外名称" value={item.label} onChange={(v) => updateLocal(item.id, { label: v })} />
                  <label className="text-xs text-stone-500">
                    说明
                    <textarea
                      value={item.description}
                      onChange={(e) => updateLocal(item.id, { description: e.target.value })}
                      rows={3}
                      className="mt-1 w-full resize-y rounded-md border border-stone-700 bg-stone-950/80 px-3 py-2 text-sm text-stone-100 outline-none focus:border-amber-500/70"
                    />
                  </label>
                  <p className="text-xs text-stone-500">
                    {item.exposed ? "已对外打开，可被 CLI / cyberspaceAI 发现" : "未打开，仅本机编排可用"}
                  </p>
                </article>
              );
            })}
          </div>
        )}
      </section>

      <AccessSetupDialog
        open={setupOpen}
        access={access}
        password={sshPassword}
        saving={savingAccess}
        onClose={() => setSetupOpen(false)}
        onPatch={patchAccess}
        onPatchLane={patchLane}
        onPassword={setSshPassword}
        onSave={() => void saveAccess()}
      />
    </div>
  );
}
