import { useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Focus,
  RotateCcw,
  Scan,
  Copy,
  Check,
  ExternalLink,
} from "lucide-react";
import { displayTime, typeColor } from "../api";
import type { Observation, ObjectMetadata } from "../types";
function Value({ value, depth = 0 }: { value: unknown; depth?: number }) {
  const childCount =
    value && typeof value === "object" ? Object.keys(value).length : 0;
  const [expanded, setExpanded] = useState(depth < 1 && childCount <= 12);
  const [visibleCount, setVisibleCount] = useState(40);
  const [long, setLong] = useState(false);
  if (value === null) return <span className="value-null">null</span>;
  if (typeof value === "object") {
    const entries = Array.isArray(value)
      ? value.map((v, i) => [String(i), v] as const)
      : Object.entries(value as Record<string, unknown>);
    return (
      <div className="nested-value">
        <button className="disclosure" onClick={() => setExpanded(!expanded)}>
          {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          <span>
            {Array.isArray(value)
              ? `数组 [${entries.length}]`
              : `对象 {${entries.length}}`}
          </span>
        </button>
        {expanded && (
          <div className="nested-content">
            {entries.slice(0, visibleCount).map(([key, val]) => (
              <div className="nested-row" key={key}>
                <span className="property-name">{key}</span>
                <Value value={val} depth={depth + 1} />
              </div>
            ))}
            {entries.length > visibleCount && (
              <button
                className="inline-link"
                onClick={() => setVisibleCount((v) => v + 40)}
              >
                再显示 40 项 · 共 {entries.length} 项
              </button>
            )}
          </div>
        )}
      </div>
    );
  }
  const text = String(value);
  return (
    <span
      className={`value-text ${typeof value === "number" ? "value-number" : ""}`}
    >
      {text.length > 180 && !long ? `${text.slice(0, 180)}…` : text}
      {text.length > 180 && (
        <button className="inline-link" onClick={() => setLong(!long)}>
          {long ? "收起" : "展开"}
        </button>
      )}
    </span>
  );
}
interface Props {
  object: Observation | null;
  metadata: ObjectMetadata | null;
  typeName: string;
  loading: boolean;
  error: string;
  onFocus: () => void;
  canFocus: boolean;
  isFocused: boolean;
  onClear: () => void;
}
export default function Inspector({
  object,
  metadata,
  typeName,
  loading,
  error,
  onFocus,
  canFocus,
  isFocused,
  onClear,
}: Props) {
  const [copied, setCopied] = useState(false);
  async function copyId() {
    if (!object) return;
    try {
      await navigator.clipboard.writeText(object.id);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }
  return (
    <aside className="inspector">
      <div className="panel-heading">
        <span>
          <Scan size={16} />
          对象详情
        </span>
        {object && (
          <button className="text-button" onClick={onClear}>
            取消选中
          </button>
        )}
      </div>
      {loading ? (
        <div className="inspector-empty">
          <span className="spinner" />
          <p>读取完整观测…</p>
        </div>
      ) : error ? (
        <div className="error-inline">{error}</div>
      ) : !object ? (
        <div className="inspector-empty">
          <div className="empty-orbit">
            <Scan size={28} />
          </div>
          <h3>让好奇心有个落点</h3>
          <p>
            点选空间中的观测点
            <br />
            或从下方目录选择对象
          </p>
          <small>完整属性 · 原始坐标 · 来源版本</small>
        </div>
      ) : (
        <div className="inspector-content">
          <div className="object-kind">
            <span style={{ background: typeColor(object.type_id) }} />
            {typeName || metadata?.type_name || `分类 ${object.type_id}`}
          </div>
          <h2>{object.name}</h2>
          <button className="object-id" title="复制对象 ID" onClick={copyId}>
            <span>{object.id}</span>
            {copied ? <Check size={13} /> : <Copy size={13} />}
          </button>
          {object.position && (
            <button
              className="focus-button"
              onClick={onFocus}
              disabled={!canFocus}
            >
              {isFocused ? <RotateCcw size={15} /> : <Focus size={15} />}
              {canFocus ? (isFocused ? "回到原处" : "聚焦此对象") : "不在当前采样中"}
            </button>
          )}
          <section className="detail-section">
            <h3>观测信息</h3>
            <dl className="detail-list">
              <div>
                <dt>观测时间</dt>
                <dd>
                  {new Date(object.timestamp_ms).toLocaleString("zh-CN", {
                    hour12: false,
                  })}
                </dd>
              </div>
              <div>
                <dt>接入时间</dt>
                <dd>{displayTime(metadata?.received_at)}</dd>
              </div>
              <div>
                <dt>分类版本</dt>
                <dd>REV {metadata?.tree_revision ?? "—"}</dd>
              </div>
              <div>
                <dt>序列标记</dt>
                <dd>{object.sequence}</dd>
              </div>
            </dl>
          </section>
          <section className="detail-section">
            <h3>空间位置</h3>
            {object.position ? (
              <>
                <div className="coordinate-frame">
                  <ExternalLink size={12} />
                  <span>{object.position.frame_id}</span>
                  <small>{object.position.unit}</small>
                </div>
                <dl className="coordinate-list">
                  {(["x", "y", "z"] as const).map((axis) => (
                    <div key={axis}>
                      <dt>{axis.toUpperCase()}</dt>
                      <dd>
                        {object.position![axis].toLocaleString("en-US", {
                          maximumFractionDigits: 5,
                        })}
                      </dd>
                    </div>
                  ))}
                </dl>
                <p className="detail-note">
                  {object.position.frame_kind} · 原始坐标
                </p>
              </>
            ) : (
              <p className="detail-note">
                此对象未提供坐标，可完整浏览与导出。
              </p>
            )}
          </section>
          <section className="detail-section">
            <h3>
              动态属性{" "}
              <span>{Object.keys(object.attributes ?? {}).length}</span>
            </h3>
            <div className="attributes">
              {Object.entries(object.attributes ?? {}).map(([key, value]) => (
                <div className="attribute" key={key}>
                  <div className="property-name">{key}</div>
                  <Value value={value} />
                </div>
              ))}
            </div>
          </section>
          {Object.keys(object).some(
            (k) =>
              ![
                "id",
                "name",
                "type_id",
                "sequence",
                "timestamp_ms",
                "position",
                "attributes",
              ].includes(k),
          ) && (
            <section className="detail-section">
              <h3>其他字段</h3>
              {Object.entries(object)
                .filter(
                  ([k]) =>
                    ![
                      "id",
                      "name",
                      "type_id",
                      "sequence",
                      "timestamp_ms",
                      "position",
                      "attributes",
                    ].includes(k),
                )
                .map(([key, value]) => (
                  <div className="attribute" key={key}>
                    <div className="property-name">{key}</div>
                    <Value value={value} />
                  </div>
                ))}
            </section>
          )}
        </div>
      )}
    </aside>
  );
}
