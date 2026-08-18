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
  created_at: string;
};

export type ComputeHealth = {
  ok: boolean;
  provider?: string;
  reason?: string;
  endpoint?: string;
  comfyui?: { ok?: boolean; provider?: string; reason?: string };
  llm?: { ok?: boolean; provider?: string; reason?: string; model?: string; models?: string[] };
};

const BASE = "/orch";

async function parse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text.slice(0, 240) || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
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
  jobs: (modality?: Modality | "all") => {
    const q = modality && modality !== "all" ? `?modality=${modality}` : "";
    return parse<{ items: Job[]; total: number }>(fetch(`${BASE}/v1/jobs${q}`));
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
  text: (job: Job) => {
    const url = artifactUrl(job);
    if (!url) return Promise.resolve("");
    return fetch(url).then((r) => r.text());
  },
};
