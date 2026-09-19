export type Modality = "text" | "image" | "video";
export type JobStatus = "queued" | "running" | "succeeded" | "failed";

export type Job = {
  id: string;
  run_id: string;
  modality: Modality;
  prompt: string;
  workflow_id: string | null;
  status: JobStatus;
  provider: string;
  output_uri: string | null;
  output_url: string | null;
  error: string | null;
  score: number | null;
  model: string | null;
  started_at: string | null;
  finished_at: string | null;
  elapsed_ms: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  output_bytes: number | null;
  output_chars: number | null;
  created_at: string;
  updated_at: string;
};

export type JobStats = {
  total: number;
  by_status: Record<JobStatus, number>;
  by_modality: Partial<Record<Modality, number>>;
  by_provider: Record<string, number>;
  success_rate: number | null;
  scored_count: number;
  avg_score: number | null;
  score_hist: Record<string, number>;
  avg_elapsed_ms: number | null;
  p50_elapsed_ms: number | null;
  p95_elapsed_ms: number | null;
  avg_prompt_tokens: number | null;
  avg_completion_tokens: number | null;
};

export type ComputeHealth = {
  ok: boolean;
  provider?: string;
  reason?: string;
  endpoint?: string;
  comfyui?: { ok?: boolean; provider?: string; reason?: string };
  llm?: { ok?: boolean; provider?: string; reason?: string; model?: string; models?: string[] };
};

export type ServiceModality = Modality;
export type ServiceProvider = "mock" | "comfyui" | "llm";

export type AccessProfile = "local" | "autodl";

export type ModalityLane = {
  enabled: boolean;
  mock: boolean;
  endpoint: string;
  model: string;
  tunnel_local: number;
  tunnel_remote: number;
};

export type AccessConfig = {
  ok?: boolean;
  profile: AccessProfile;
  mock_text: boolean;
  mock_image: boolean;
  mock_video: boolean;
  comfyui_endpoint: string;
  llm_base_url: string;
  llm_model: string;
  local_comfyui_endpoint: string;
  local_llm_base_url: string;
  local_llm_model: string;
  autodl_comfyui_endpoint: string;
  autodl_llm_base_url: string;
  autodl_llm_model: string;
  autodl_ssh_host: string;
  autodl_ssh_port: number;
  autodl_ssh_user: string;
  autodl_ssh_auth: "password" | "key";
  autodl_ssh_key_path: string;
  autodl_ssh_password_set?: boolean;
  autodl_ssh_password?: string;
  local_text: ModalityLane;
  local_image: ModalityLane;
  local_video: ModalityLane;
  autodl_text: ModalityLane;
  autodl_image: ModalityLane;
  autodl_video: ModalityLane;
  orch_host?: string;
  orch_port?: number;
};

export type ExposedService = {
  id: string;
  modality: ServiceModality;
  label: string;
  provider: ServiceProvider;
  workflow_id: string;
  exposed: boolean;
  description: string;
  invoke?: {
    group: string;
    action: string;
    args: { modality: ServiceModality; workflow: string };
  };
};

const BASE = "/orch";

function jobQuery(modality?: Modality | "all") {
  const params = new URLSearchParams();
  if (modality && modality !== "all") params.set("modality", modality);
  params.set("exclude_provider", "mock");
  return params.toString();
}

function mapFetchError(err: unknown): never {
  if (err instanceof TypeError) {
    throw new Error("编排连不上（Failed to fetch）。请确认平台已启动：http://127.0.0.1:3190/");
  }
  throw err;
}

async function parse<T>(res: Response | Promise<Response>): Promise<T> {
  let response: Response;
  try {
    response = await res;
  } catch (err) {
    mapFetchError(err);
  }
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text.slice(0, 240) || `HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function artifactUrl(job: Job): string | null {
  if (job.output_url) return `${BASE}${job.output_url}`;
  if (job.id) return `${BASE}/v1/jobs/${job.id}/file`;
  return null;
}

export const api = {
  health: () =>
    parse<{
      ok: boolean;
      mock: boolean;
      mock_text?: boolean;
      mock_image?: boolean;
      port: number;
    }>(fetch(`${BASE}/health`)),
  compute: () => parse<ComputeHealth>(fetch(`${BASE}/v1/compute/health`)),
  services: () => parse<{ ok: boolean; items: ExposedService[] }>(fetch(`${BASE}/v1/services`)),
  saveServices: (items: ExposedService[]) =>
    parse<{ ok: boolean; items: ExposedService[] }>(
      fetch(`${BASE}/v1/services`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items }),
      }),
    ),
  patchService: (id: string, body: Partial<Pick<ExposedService, "exposed" | "label" | "description">>) =>
    parse<{ ok: boolean; item: ExposedService; items: ExposedService[] }>(
      fetch(`${BASE}/v1/services/${encodeURIComponent(id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    ),
  access: () => parse<AccessConfig>(fetch(`${BASE}/v1/access`)),
  saveAccess: (
    body: Omit<
      AccessConfig,
      "ok" | "orch_host" | "orch_port" | "comfyui_endpoint" | "llm_base_url" | "llm_model" | "autodl_ssh_password_set"
    >,
  ) =>
    parse<AccessConfig>(
      fetch(`${BASE}/v1/access`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    ),
  jobs: (modality?: Modality | "all") => {
    const q = jobQuery(modality);
    return parse<{ items: Job[]; total: number }>(fetch(`${BASE}/v1/jobs?${q}`));
  },
  stats: (modality?: Modality | "all") => {
    const q = jobQuery(modality);
    return parse<JobStats>(fetch(`${BASE}/v1/jobs/stats?${q}`));
  },
  create: (body: { modality: Modality; prompt: string; workflow_id?: string }) =>
    parse<Job>(
      fetch(`${BASE}/v1/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    ),
  score: (id: string, score: number) =>
    parse<Job>(
      fetch(`${BASE}/v1/jobs/${id}/score`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ score }),
      }),
    ),
  remove: (id: string) =>
    parse<{ ok: boolean; removed: string }>(fetch(`${BASE}/v1/jobs/${id}`, { method: "DELETE" })),
  clearMock: () =>
    parse<{ ok: boolean; removed: number; remaining: number }>(
      fetch(`${BASE}/v1/jobs?provider=mock`, { method: "DELETE" }),
    ),
  text: (job: Job) => {
    const url = artifactUrl(job);
    if (!url) return Promise.resolve("");
    return fetch(url).then((r) => r.text());
  },
};
