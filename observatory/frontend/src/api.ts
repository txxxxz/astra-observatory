import type { Filters } from "./types";
export async function api<T>(path: string, signal?: AbortSignal): Promise<T> {
  const controller = new AbortController();
  let timedOut = false;
  const abort = () => controller.abort();
  if (signal?.aborted) abort();
  signal?.addEventListener("abort", abort, { once: true });
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, 10000);
  try {
    const response = await fetch(path, {
      signal: controller.signal,
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      let detail = "";
      try {
        const data = await response.json();
        detail =
          typeof data.detail === "string"
            ? data.detail
            : JSON.stringify(data.detail ?? data);
      } catch {
        detail = response.statusText;
      }
      throw new Error(`${response.status} · ${detail || "请求失败"}`);
    }
    return (await response.json()) as T;
  } catch (error) {
    if (timedOut && !signal?.aborted) throw new Error("请求超时，请稍后重试");
    throw error;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", abort);
  }
}
export const runPath = (run: string) => `/api/runs/${encodeURIComponent(run)}`;
export function filterParams(filters: Filters) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== "" && value !== undefined) query.set(key, String(value));
  }
  return query;
}
export function displayNumber(n?: number) {
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(
    n ?? 0,
  );
}
export function displayTime(value?: string | number) {
  if (value === undefined || value === null) return "—";
  const numeric = typeof value === "number" ? value : Number(value);
  const date =
    Number.isFinite(numeric) && numeric !== 0
      ? new Date(numeric < 1e12 ? numeric * 1000 : numeric)
      : new Date(value);
  return Number.isNaN(date.getTime())
    ? "—"
    : date.toLocaleTimeString("zh-CN", { hour12: false });
}
export function displayBytes(value?: number) {
  const n = value ?? 0;
  return n > 1024 ** 3
    ? `${(n / 1024 ** 3).toFixed(2)} GiB`
    : n > 1024 ** 2
      ? `${(n / 1024 ** 2).toFixed(1)} MiB`
      : `${(n / 1024).toFixed(1)} KiB`;
}
export const frameKey = (frame: {
  frame_id: string;
  frame_kind: string;
  unit: string;
}) => JSON.stringify([frame.frame_id, frame.frame_kind, frame.unit]);
export const typeColor = (id: number) =>
  ["#64dbc5", "#8b9cf7", "#eeb97a", "#d58dbf", "#92cfae", "#79b5e5", "#d9d28c"][
    Math.abs(id) % 7
  ];
