import {
  ChevronDown,
  ChevronRight,
  Layers3,
  Radio,
  FolderTree,
} from "lucide-react";
import { useMemo, useState } from "react";
import { displayNumber, typeColor } from "../api";
import type { TypeNode, Change } from "../types";
interface Props {
  items: TypeNode[];
  changes: Change[];
  selected: string;
  onSelect: (id: string) => void;
  total: number;
  revision: number;
  loading: boolean;
  descendants: boolean;
  onDescendants: (v: boolean) => void;
}
export default function CategoryTree({
  items,
  changes,
  selected,
  onSelect,
  total,
  revision,
  loading,
  descendants,
  onDescendants,
}: Props) {
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());
  const children = useMemo(() => {
    const map = new Map<number, TypeNode[]>();
    const ids = new Set(items.map((item) => item.type_id));
    for (const item of items) {
      const parent = ids.has(item.parent_id) ? item.parent_id : 0;
      map.set(parent, [...(map.get(parent) ?? []), item]);
    }
    return map;
  }, [items]);
  const render = (
    node: TypeNode,
    depth: number,
    trail: Set<number>,
  ): React.ReactNode => {
    if (trail.has(node.type_id)) return null;
    const sub = children.get(node.type_id) ?? [];
    const open = !collapsed.has(node.type_id);
    return (
      <div key={node.type_id}>
        <div
          className={`tree-row ${selected === String(node.type_id) ? "active" : ""}`}
          style={{ paddingLeft: 12 + depth * 13 }}
        >
          <button
            className="tree-toggle"
            disabled={!sub.length}
            aria-label={`${open ? "收起" : "展开"}${node.name}`}
            onClick={() =>
              setCollapsed((old) => {
                const next = new Set(old);
                if (next.has(node.type_id)) next.delete(node.type_id);
                else next.add(node.type_id);
                return next;
              })
            }
          >
            {sub.length ? (
              open ? (
                <ChevronDown size={13} />
              ) : (
                <ChevronRight size={13} />
              )
            ) : (
              <span
                className="tree-dot"
                style={{ background: typeColor(node.type_id) }}
              />
            )}
          </button>
          <button
            className="tree-label"
            title={node.name}
            onClick={() => onSelect(String(node.type_id))}
          >
            <span>{node.name}</span>
            <small>
              {displayNumber(
                descendants
                  ? (node.subtree_count ?? node.object_count)
                  : node.object_count,
              )}
            </small>
          </button>
        </div>
        {open &&
          sub.map((n) =>
            render(n, depth + 1, new Set([...trail, node.type_id])),
          )}
      </div>
    );
  };
  return (
    <aside className="category-panel">
      <div className="panel-heading">
        <span>
          <FolderTree size={16} />
          分类目录
        </span>
        <small>{items.length} 类</small>
      </div>
      <button
        className={`all-objects ${!selected ? "active" : ""}`}
        onClick={() => onSelect("")}
      >
        <span>
          <Layers3 size={16} />
          全部对象
        </span>
        <strong>{displayNumber(total)}</strong>
      </button>
      <label className="check-label subtree-check">
        <input
          type="checkbox"
          checked={descendants}
          onChange={(e) => onDescendants(e.target.checked)}
        />
        包含下级分类
      </label>
      <div className="tree-scroll">
        {loading && items.length === 0 ? (
          <p className="subtle-state">正在读取分类…</p>
        ) : items.length === 0 ? (
          <div className="tree-empty">
            <FolderTree size={24} />
            <p>等待分类消息</p>
            <small>接入后自动建立探索目录</small>
          </div>
        ) : (
          (children.get(0) ?? []).map((n) => render(n, 0, new Set()))
        )}
      </div>
      <section className="changes">
        <div className="panel-heading">
          <span>
            <Radio size={14} />
            分类演化
          </span>
          <small>REV {revision}</small>
        </div>
        <div className="changes-scroll">
          {changes.length ? (
            changes.slice(0, 6).map((change, i) => (
              <div className="change-item" key={`${change.revision}-${i}`}>
                <span className="change-mark" />
                <div>
                  <small>版本 {change.revision}</small>
                  {change.changes.slice(0, 2).map((c, index) => (
                    <p key={index}>
                      {(
                        {
                          create: "新增",
                          rename: "更名",
                          move: "迁移",
                        } as Record<string, string>
                      )[c.op] ?? c.op}{" "}
                      · {c.node.name}
                    </p>
                  ))}
                  {change.changes.length > 2 && (
                    <small>另有 {change.changes.length - 2} 项变更</small>
                  )}
                </div>
              </div>
            ))
          ) : (
            <p className="subtle-state">暂无分类变更</p>
          )}
        </div>
      </section>
      <div className="sidebar-foot">
        <span className="tiny-dot" />
        当前分类视图
      </div>
    </aside>
  );
}
