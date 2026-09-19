"use client";

import type { AccessConfig, AccessProfile, Modality, ModalityLane } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { Loader2 } from "lucide-react";

const PROFILES: { id: AccessProfile; title: string; desc: string }[] = [
  { id: "local", title: "本地服务", desc: "本机或局域网 GPU，直连地址" },
  { id: "autodl", title: "autodl租赁", desc: "SSH 隧道后访问实例" },
];

const LANES: {
  mod: Modality;
  title: string;
  modelLabel: string;
  placeholder: string;
}[] = [
  { mod: "text", title: "文本", modelLabel: "模型", placeholder: "qwen3.8-27b" },
  { mod: "image", title: "图片", modelLabel: "工作流", placeholder: "t2i.demo" },
  { mod: "video", title: "视频", modelLabel: "工作流", placeholder: "t2v.u03" },
];

function Field({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <label className="text-xs text-stone-500">
      {label}
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete={type === "password" ? "new-password" : "off"}
        className="mt-1 w-full rounded-md border border-stone-700 bg-stone-950/80 px-3 py-2 text-sm text-stone-100 outline-none focus:border-amber-500/70"
      />
    </label>
  );
}

export function SshFields({
  access,
  password,
  onPatch,
  onPassword,
}: {
  access: AccessConfig;
  password: string;
  onPatch: (partial: Partial<AccessConfig>) => void;
  onPassword: (value: string) => void;
}) {
  return (
    <div className="grid gap-3">
      <Field
        label="SSH Host"
        value={access.autodl_ssh_host}
        onChange={(v) => onPatch({ autodl_ssh_host: v })}
        placeholder="connect.westc.seetacloud.com"
      />
      <label className="text-xs text-stone-500">
        端口
        <input
          type="number"
          min={0}
          max={65535}
          value={access.autodl_ssh_port || ""}
          onChange={(e) => onPatch({ autodl_ssh_port: Number(e.target.value) || 0 })}
          placeholder="开机后看 AutoDL 控制台"
          className="mt-1 w-full rounded-md border border-stone-700 bg-stone-950/80 px-3 py-2 text-sm text-stone-100 outline-none focus:border-amber-500/70"
        />
      </label>
      <Field label="用户" value={access.autodl_ssh_user} onChange={(v) => onPatch({ autodl_ssh_user: v })} placeholder="root" />
      <div className="flex gap-1 rounded-md bg-stone-950 p-1 text-xs">
        {(["password", "key"] as const).map((auth) => (
          <button
            key={auth}
            type="button"
            onClick={() => onPatch({ autodl_ssh_auth: auth })}
            className={cn(
              "flex-1 rounded px-2 py-1.5",
              access.autodl_ssh_auth === auth ? "bg-stone-700 text-white" : "text-stone-400 hover:text-stone-200",
            )}
          >
            {auth === "password" ? "密码" : "私钥"}
          </button>
        ))}
      </div>
      {access.autodl_ssh_auth === "key" ? (
        <Field
          label="私钥路径"
          value={access.autodl_ssh_key_path}
          onChange={(v) => onPatch({ autodl_ssh_key_path: v })}
          placeholder="~/.ssh/id_rsa"
        />
      ) : (
        <Field
          label={access.autodl_ssh_password_set ? "密码（已保存，留空不改）" : "密码"}
          value={password}
          onChange={onPassword}
          type="password"
          placeholder={access.autodl_ssh_password_set ? "••••••••" : "SSH 密码"}
        />
      )}
    </div>
  );
}

function laneOf(access: AccessConfig, profile: AccessProfile, mod: Modality): ModalityLane {
  return access[`${profile}_${mod}`];
}

export function AccessSetupDialog({
  open,
  access,
  password,
  saving,
  onClose,
  onPatch,
  onPatchLane,
  onPassword,
  onSave,
}: {
  open: boolean;
  access: AccessConfig;
  password: string;
  saving: boolean;
  onClose: () => void;
  onPatch: (partial: Partial<AccessConfig>) => void;
  onPatchLane: (profile: AccessProfile, mod: Modality, partial: Partial<ModalityLane>) => void;
  onPassword: (value: string) => void;
  onSave: () => void;
}) {
  if (!open) return null;
  const profile = access.profile;
  const llm = profile === "local" ? access.local_llm_base_url : access.autodl_llm_base_url;
  const comfy = profile === "local" ? access.local_comfyui_endpoint : access.autodl_comfyui_endpoint;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 px-4 py-10" onClick={onClose}>
      <div
        role="dialog"
        aria-labelledby="access-setup-title"
        className="w-full max-w-4xl rounded-xl border border-stone-800 bg-stone-950 p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="access-setup-title" className="text-lg font-medium">
          配置
        </h2>
        <p className="mt-1 text-sm text-stone-400">编排定义 Mock 与模型；本地 / 租赁只配接入地址与 SSH。</p>

        <div className="mt-5 space-y-5">
          <div>
            <p className="mb-2 text-xs text-stone-500">接入方式</p>
            <div className="grid gap-2 sm:grid-cols-2">
              {PROFILES.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => onPatch({ profile: item.id })}
                  className={cn(
                    "rounded-lg border px-3 py-3 text-left",
                    access.profile === item.id ? "border-amber-700/80 bg-stone-900" : "border-stone-800 hover:bg-stone-900/60",
                  )}
                >
                  <span className="text-sm text-stone-100">{item.title}</span>
                  <span className="mt-1 block text-xs text-stone-500">{item.desc}</span>
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="mb-2 text-xs text-stone-500">编排：权限与模型（随当前接入路径）</p>
            <div className="grid gap-3 md:grid-cols-3">
              {LANES.map((item) => {
                const lane = laneOf(access, profile, item.mod);
                return (
                  <div key={item.mod} className="space-y-3 rounded-lg border border-stone-800 p-4">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm text-stone-200">{item.title}</p>
                      <label className="flex items-center gap-2 text-xs text-stone-400">
                        Mock
                        <input
                          type="checkbox"
                          checked={lane.mock || !lane.enabled}
                          onChange={() => onPatchLane(profile, item.mod, { mock: !(lane.mock || !lane.enabled) })}
                        />
                      </label>
                    </div>
                    <Field
                      label={item.modelLabel}
                      value={lane.model}
                      onChange={(v) => onPatchLane(profile, item.mod, { model: v })}
                      placeholder={item.placeholder}
                    />
                  </div>
                );
              })}
            </div>
          </div>

          <div className="space-y-3 rounded-lg border border-stone-800 p-4">
            <p className="text-sm text-stone-200">{profile === "local" ? "本地服务" : "autodl租赁"}地址</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field
                label="LLM 地址"
                value={llm}
                onChange={(v) =>
                  onPatchLane(profile, "text", { endpoint: v })
                }
              />
              <Field
                label="ComfyUI 地址"
                value={comfy}
                onChange={(v) => {
                  onPatchLane(profile, "image", { endpoint: v });
                  onPatchLane(profile, "video", { endpoint: v });
                }}
              />
            </div>
          </div>

          {profile === "autodl" ? (
            <div className="rounded-lg border border-stone-800 p-4">
              <p className="mb-3 text-sm text-stone-200">租赁 SSH 通道与密钥（文/图/视频共用）</p>
              <SshFields access={access} password={password} onPatch={onPatch} onPassword={onPassword} />
            </div>
          ) : null}
        </div>

        <div className="mt-6 flex justify-end gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={onClose}>
            取消
          </Button>
          <Button type="button" size="sm" onClick={onSave} disabled={saving}>
            {saving ? <Loader2 className="size-4 animate-spin" /> : null}
            {saving ? "保存中" : "保存"}
          </Button>
        </div>
      </div>
    </div>
  );
}
