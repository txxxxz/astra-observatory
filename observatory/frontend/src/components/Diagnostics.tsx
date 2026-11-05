import { useEffect, useState } from "react";
import { X, ShieldCheck, ArrowLeft, AlertTriangle } from "lucide-react";
import { api, runPath, displayTime, displayNumber } from "../api";
import type { Message, Metrics } from "../types";
export default function Diagnostics({
  run,
  metrics,
  onClose,
}: {
  run: string;
  metrics: Metrics | null;
  onClose: () => void;
}) {
  const [status, setStatus] = useState("quarantined");
  const [items, setItems] = useState<Message[]>([]);
  const [detail, setDetail] = useState<Message | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    setError("");
    api<{ items: Message[] }>(
      `${runPath(run)}/messages?limit=50${status ? `&status=${status}` : ""}`,
      ctrl.signal,
    )
      .then((v) => setItems(v.items))
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false);
      });
    return () => ctrl.abort();
  }, [run, status]);
  useEffect(() => {
    const listener = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, [onClose]);
  async function openDetail(id: number) {
    setError("");
    try {
      setDetail(await api<Message>(`${runPath(run)}/messages/${id}`));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <div
      className="modal-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <section
        className="diagnostics"
        role="dialog"
        aria-modal="true"
        aria-label="接入与异常记录"
      >
        <header>
          <div>
            <ShieldCheck size={20} />
            <h2>接入与异常记录</h2>
          </div>
          <button
            className="icon-button"
            autoFocus
            onClick={onClose}
            aria-label="关闭接入记录"
          >
            <X size={20} />
          </button>
        </header>
        <div className="diagnostic-stats">
          <div>
            <span>可靠保存的消息</span>
            <strong>{displayNumber(metrics?.message_count)}</strong>
          </div>
          <div>
            <span>重复投递</span>
            <strong>{displayNumber(metrics?.duplicate_count)}</strong>
          </div>
          <div>
            <span>隔离 / 冲突</span>
            <strong className="warning-text">
              {displayNumber(metrics?.quarantined_count)} /{" "}
              {displayNumber(metrics?.conflict_count)}
            </strong>
          </div>
        </div>
        <p className="diagnostic-note">
          <AlertTriangle size={14} />
          隔离消息已完整落盘，未进入对象视图。分类缺口、字段异常和未确认的对象变更会保留原因。
        </p>
        {detail ? (
          <div className="message-detail">
            <button className="text-button" onClick={() => setDetail(null)}>
              <ArrowLeft size={14} />
              返回记录
            </button>
            <pre>{JSON.stringify(detail, null, 2)}</pre>
          </div>
        ) : (
          <>
            <div className="diagnostic-tabs">
              {[
                ["quarantined", "隔离"],
                ["conflict", "冲突"],
                ["applied", "已应用"],
                ["", "全部"],
              ].map(([value, label]) => (
                <button
                  key={value}
                  className={status === value ? "active" : ""}
                  onClick={() => setStatus(value)}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="message-list">
              {loading ? (
                <p className="subtle-state">正在读取消息…</p>
              ) : items.length === 0 ? (
                <p className="subtle-state">此状态暂无记录</p>
              ) : (
                items.map((item) => (
                  <button
                    className="message-row"
                    key={item.id}
                    onClick={() => openDetail(item.id)}
                  >
                    <span className={`message-status ${item.status}`}>
                      {item.status}
                    </span>
                    <span>
                      <strong>
                        {item.kind} · {item.message_key}
                      </strong>
                      <small>
                        {item.reason ?? `${item.object_count ?? 0} 个对象条目`}
                      </small>
                    </span>
                    <time>{displayTime(item.received_at)}</time>
                  </button>
                ))
              )}
            </div>
          </>
        )}
        {error && <p className="error-inline">{error}</p>}
        <footer>显示最近 50 条 · 点击记录查看原始消息</footer>
      </section>
    </div>
  );
}
