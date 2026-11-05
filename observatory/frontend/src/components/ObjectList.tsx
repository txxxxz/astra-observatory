import {
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  ChevronDown,
  ChevronUp,
  List,
  Search,
  X,
} from "lucide-react";
import { displayNumber, typeColor } from "../api";
import type { ObjectItem } from "../types";
interface Props {
  items: ObjectItem[];
  loading: boolean;
  error: string;
  selected: string;
  onSelect: (id: string) => void;
  nextCursor: string | null;
  page: number;
  onNext: () => void;
  onPrevious: () => void;
  exportUrl: string;
  search: string;
  searchMode: "name" | "id";
  onSearch: (v: string) => void;
  onMode: (v: "name" | "id") => void;
  categoryName: string;
  onClearCategory: () => void;
  collapsed: boolean;
  onCollapse: () => void;
  refreshing: boolean;
  frameFilter: boolean;
  onFrameFilter: (value: boolean) => void;
  hasFrame: boolean;
}
export default function ObjectList(p: Props) {
  return (
    <section className={`object-list ${p.collapsed ? "collapsed" : ""}`}>
      <div className="list-heading">
        <button className="list-heading-title" onClick={p.onCollapse}>
          <List size={16} />
          <span>对象目录</span>
          <small>{displayNumber(p.items.length)} 条</small>
          {p.collapsed ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
        <a
          className={`export-button ${!p.exportUrl ? "disabled" : ""}`}
          href={p.exportUrl || undefined}
          download
          aria-label="导出筛选结果 NDJSON"
        >
          <ArrowDownToLine size={14} />
          <span>导出筛选结果</span>
          <small>NDJSON</small>
        </a>
      </div>
      {!p.collapsed && (
        <>
          <div className="list-filters">
            <div className="search-input">
              <Search size={14} />
              <input
                aria-label={
                  p.searchMode === "name" ? "按名称前缀搜索" : "按对象 ID 搜索"
                }
                placeholder={
                  p.searchMode === "name"
                    ? "按名称前缀搜索…"
                    : "输入完整对象 ID…"
                }
                value={p.search}
                onChange={(e) => p.onSearch(e.target.value)}
              />
              {p.search && (
                <button
                  className="icon-button"
                  aria-label="清除搜索"
                  onClick={() => p.onSearch("")}
                >
                  <X size={12} />
                </button>
              )}
              <select
                aria-label="搜索方式"
                value={p.searchMode}
                onChange={(e) => p.onMode(e.target.value as "name" | "id")}
              >
                <option value="name">名称前缀</option>
                <option value="id">对象 ID</option>
              </select>
            </div>
            <label className="check-label list-frame-filter">
              <input
                type="checkbox"
                checked={p.frameFilter}
                onChange={(e) => p.onFrameFilter(e.target.checked)}
                disabled={!p.hasFrame}
              />
              仅当前坐标系
            </label>
            {p.categoryName && (
              <button className="filter-tag" onClick={p.onClearCategory}>
                {p.categoryName}
                <X size={12} />
              </button>
            )}
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>对象名称</th>
                  <th>当前分类</th>
                  <th>坐标系</th>
                  <th>序列</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {p.items.map((item) => (
                  <tr
                    key={item.id}
                    className={p.selected === item.id ? "selected" : ""}
                    onClick={() => p.onSelect(item.id)}
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") p.onSelect(item.id);
                    }}
                    aria-selected={p.selected === item.id}
                  >
                    <td>
                      <span
                        className="object-dot"
                        style={{ background: typeColor(item.type_id) }}
                      />
                      <span className="table-name">{item.name}</span>
                      <small className="table-id">{item.id}</small>
                    </td>
                    <td>{item.type_name ?? `分类 ${item.type_id}`}</td>
                    <td>
                      {item.position ? (
                        <span className="frame-tag">
                          {item.position.frame_id}
                          <small>{item.position.unit}</small>
                        </span>
                      ) : (
                        <span className="muted">无坐标</span>
                      )}
                    </td>
                    <td className="mono">{item.sequence}</td>
                    <td>
                      <ArrowRight size={13} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {p.loading && p.items.length === 0 ? (
              <div className="table-state">
                <span className="spinner" />
                正在读取对象…
              </div>
            ) : p.error ? (
              <div className="table-state error-inline">{p.error}</div>
            ) : p.items.length === 0 ? (
              <div className="table-state">
                暂无匹配对象 · 可调整分类或搜索条件
              </div>
            ) : null}
          </div>
          <div className="list-footer">
            <span>
              <span className={`tiny-dot ${p.refreshing ? "pending" : ""}`} />
              {p.refreshing ? "正在读取…" : "稳定浏览快照"}
            </span>
            <div className="pagination">
              <button
                className="icon-button"
                aria-label="上一页"
                disabled={p.page === 0 || p.loading}
                onClick={p.onPrevious}
              >
                <ArrowLeft size={14} />
              </button>
              <span>第 {p.page + 1} 页</span>
              <button
                className="icon-button"
                aria-label="下一页"
                disabled={!p.nextCursor || p.loading}
                onClick={p.onNext}
              >
                <ArrowRight size={14} />
              </button>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
