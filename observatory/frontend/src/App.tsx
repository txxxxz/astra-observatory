import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertCircle,
  ArrowUpRight,
  Check,
  ChevronDown,
  Database,
  FolderTree,
  Layers3,
  Orbit,
  RefreshCw,
  Scan,
  ShieldCheck,
  Wifi,
  WifiOff,
  X,
} from "lucide-react";
import {
  api,
  displayBytes,
  displayNumber,
  displayTime,
  filterParams,
  frameKey,
  runPath,
} from "./api";
import type {
  Filters,
  Frame,
  Metrics,
  ObjectDetail,
  ObjectPage,
  Point,
  PointsResponse,
  Run,
  TypeResponse,
} from "./types";
import { emptyFilters } from "./types";
import CategoryTree from "./components/CategoryTree";
import Inspector from "./components/Inspector";
import ObjectList from "./components/ObjectList";
import Diagnostics from "./components/Diagnostics";
import UniverseScene from "./components/UniverseScene";
import type { SceneHandle } from "./components/UniverseScene";
const emptyPage: ObjectPage = { items: [], next_cursor: null, snapshot_max: 0 };
const emptyTypes: TypeResponse = { revision: 0, items: [], changes: [] };
export default function App() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [run, setRun] = useState("");
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [types, setTypes] = useState<TypeResponse>(emptyTypes);
  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const [frame, setFrame] = useState<Frame | null>(null);
  const [frameFilter, setFrameFilter] = useState(false);
  const [search, setSearch] = useState("");
  const [searchMode, setSearchMode] = useState<"name" | "id">("name");
  const [page, setPage] = useState<ObjectPage>(emptyPage);
  const [cursors, setCursors] = useState<Array<string | undefined>>([
    undefined,
  ]);
  const snapshot = useRef<number | undefined>(undefined);
  const [pageIndex, setPageIndex] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [viewCount, setViewCount] = useState<number | null>(null);
  const [points, setPoints] = useState<Point[]>([]);
  const [pointTotal, setPointTotal] = useState(0);
  const [selected, setSelected] = useState("");
  const [detail, setDetail] = useState<ObjectDetail | null>(null);
  const [errors, setErrors] = useState({
    connection: "",
    list: "",
    points: "",
    detail: "",
    types: "",
  });
  const [loading, setLoading] = useState({
    runs: true,
    list: false,
    points: false,
    detail: false,
    types: false,
  });
  const [lastSuccess, setLastSuccess] = useState(0);
  const [now, setNow] = useState(Date.now());
  const [diagnostics, setDiagnostics] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [mobilePanel, setMobilePanel] = useState<"scene" | "types" | "detail">(
    "scene",
  );
  const scene = useRef<SceneHandle>(null);
  const activeRun = useRef(run);
  activeRun.current = run;
  useEffect(() => {
    let disposed = false;
    let inFlight = false;
    const poll = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const result = await api<{ items: Run[] }>("/api/runs");
        if (disposed) return;
        setRuns(result.items);
        setRun((old) => old || result.items[0]?.test_id || "");
        if (!activeRun.current) {
          setErrors((old) => ({ ...old, connection: "" }));
          setLastSuccess(Date.now());
        }
      } catch (e) {
        if (!disposed && !activeRun.current)
          setErrors((old) => ({ ...old, connection: (e as Error).message }));
      } finally {
        inFlight = false;
        if (!disposed) setLoading((old) => ({ ...old, runs: false }));
      }
    };
    void poll();
    const id = setInterval(poll, 5000);
    return () => {
      disposed = true;
      clearInterval(id);
    };
  }, []);
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  useEffect(() => {
    setMetrics(null);
    setTypes(emptyTypes);
    setFilters(emptyFilters);
    setFrame(null);
    setFrameFilter(false);
    setSearch("");
    setPage(emptyPage);
    setCursors([undefined]);
    setPageIndex(0);
    snapshot.current = undefined;
    setSelected("");
    setDetail(null);
    setPoints([]);
    setPointTotal(0);
    setViewCount(null);
    setErrors((old) => ({
      ...old,
      list: "",
      points: "",
      detail: "",
      types: "",
    }));
  }, [run]);
  useEffect(() => {
    if (!run) return;
    let disposed = false;
    let inFlight = false;
    const ctrl = new AbortController();
    const poll = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const value = await api<Metrics>(
          `${runPath(run)}/metrics`,
          ctrl.signal,
        );
        if (disposed) return;
        setMetrics(value);
        setViewCount((old) => (old === null ? value.object_count : old));
        setFrame((old) =>
          old && value.frames.some((f) => frameKey(f) === frameKey(old))
            ? old
            : (value.frames.find((f) => f.frame_kind === "galactic") ??
              value.frames[0] ??
              null),
        );
        setLastSuccess(Date.now());
        setErrors((old) => ({ ...old, connection: "" }));
      } catch (e) {
        if (!disposed && (e as Error).name !== "AbortError")
          setErrors((old) => ({ ...old, connection: (e as Error).message }));
      } finally {
        inFlight = false;
      }
    };
    void poll();
    const id = setInterval(poll, 3000);
    return () => {
      disposed = true;
      ctrl.abort();
      clearInterval(id);
    };
  }, [run]);
  useEffect(() => {
    if (!run) return;
    const ctrl = new AbortController();
    setLoading((old) => ({ ...old, types: true }));
    api<TypeResponse>(`${runPath(run)}/types`, ctrl.signal)
      .then((value) => {
        setTypes({
          ...value,
          changes: [...(value.changes ?? [])].sort(
            (a, b) => b.revision - a.revision,
          ),
        });
        setErrors((old) => ({ ...old, types: "" }));
      })
      .catch((e) => {
        if (e.name !== "AbortError")
          setErrors((old) => ({ ...old, types: e.message }));
      })
      .finally(() => {
        if (!ctrl.signal.aborted)
          setLoading((old) => ({ ...old, types: false }));
      });
    return () => ctrl.abort();
  }, [run, metrics?.revision, refresh]);
  useEffect(() => {
    const id = setTimeout(
      () =>
        setFilters((old) => ({
          ...old,
          name_prefix: searchMode === "name" ? search : "",
          object_id: searchMode === "id" ? search : "",
        })),
      300,
    );
    return () => clearTimeout(id);
  }, [search, searchMode]);
  const effectiveFilters = useMemo(
    () => ({
      ...filters,
      ...(frameFilter && frame
        ? {
            frame_id: frame.frame_id,
            frame_kind: frame.frame_kind,
            unit: frame.unit,
          }
        : { frame_id: "", frame_kind: "", unit: "" }),
    }),
    [filters, frameFilter, frame],
  );
  const filterKey = filterParams(effectiveFilters).toString();
  const filteredRevision = filters.type_id ? metrics?.revision : undefined;
  useEffect(() => {
    setPageIndex(0);
    setCursors([undefined]);
    snapshot.current = undefined;
    setPage(emptyPage);
  }, [filterKey, run, refresh, filteredRevision]);
  useEffect(() => {
    if (!run) return;
    const ctrl = new AbortController();
    const query = filterParams(effectiveFilters);
    query.set("limit", "50");
    const cursor = cursors[pageIndex];
    if (cursor) query.set("cursor", cursor);
    if (snapshot.current !== undefined)
      query.set("snapshot_max", String(snapshot.current));
    setLoading((old) => ({ ...old, list: true }));
    setErrors((old) => ({ ...old, list: "" }));
    api<ObjectPage>(`${runPath(run)}/objects?${query}`, ctrl.signal)
      .then((value) => {
        setPage(value);
        if (pageIndex === 0) snapshot.current = value.snapshot_max;
      })
      .catch((e) => {
        if (e.name !== "AbortError")
          setErrors((old) => ({ ...old, list: e.message }));
      })
      .finally(() => {
        if (!ctrl.signal.aborted)
          setLoading((old) => ({ ...old, list: false }));
      });
    return () => ctrl.abort();
    // Snapshot/cursor are established by a successful request and intentionally not polling dependencies.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run, filterKey, pageIndex, refresh, filteredRevision]);
  useEffect(() => {
    setPoints([]);
    setPointTotal(0);
    if (!run || !frame) {
      setLoading((old) => ({ ...old, points: false }));
      return;
    }
    const ctrl = new AbortController();
    const query = filterParams({
      ...filters,
      frame_id: frame.frame_id,
      frame_kind: frame.frame_kind,
      unit: frame.unit,
    });
    query.set("limit", "3000");
    setLoading((old) => ({ ...old, points: true }));
    setErrors((old) => ({ ...old, points: "" }));
    api<PointsResponse>(`${runPath(run)}/points?${query}`, ctrl.signal)
      .then((value) => {
        setPoints(value.items);
        setPointTotal(value.total);
      })
      .catch((e) => {
        if (e.name !== "AbortError")
          setErrors((old) => ({ ...old, points: e.message }));
      })
      .finally(() => {
        if (!ctrl.signal.aborted)
          setLoading((old) => ({ ...old, points: false }));
      });
    return () => ctrl.abort();
  }, [
    run,
    frame?.frame_id,
    frame?.frame_kind,
    frame?.unit,
    filters.type_id,
    filters.descendants,
    filters.name_prefix,
    filters.object_id,
    filteredRevision,
    refresh,
  ]);
  useEffect(() => {
    if (!run || !selected) {
      setDetail(null);
      setLoading((old) => ({ ...old, detail: false }));
      setErrors((old) => ({ ...old, detail: "" }));
      return;
    }
    const ctrl = new AbortController();
    setLoading((old) => ({ ...old, detail: true }));
    setErrors((old) => ({ ...old, detail: "" }));
    api<ObjectDetail>(
      `${runPath(run)}/objects/${encodeURIComponent(selected)}`,
      ctrl.signal,
    )
      .then(setDetail)
      .catch((e) => {
        if (e.name !== "AbortError")
          setErrors((old) => ({ ...old, detail: e.message }));
      })
      .finally(() => {
        if (!ctrl.signal.aborted)
          setLoading((old) => ({ ...old, detail: false }));
      });
    return () => ctrl.abort();
  }, [run, selected]);
  const selectObject = useCallback((id: string) => {
    setSelected(id);
    if (window.innerWidth <= 760) setMobilePanel("detail");
  }, []);
  const refreshView = () => {
    setViewCount(metrics?.object_count ?? 0);
    setRefresh((v) => v + 1);
  };
  const nextPage = () => {
    if (!page.next_cursor) return;
    setCursors((old) => [...old.slice(0, pageIndex + 1), page.next_cursor!]);
    setPageIndex((v) => v + 1);
  };
  const stale = lastSuccess > 0 && now - lastSuccess > 15000;
  const connected = !errors.connection && !stale;
  const additions = Math.max(
    0,
    (metrics?.object_count ?? 0) - (viewCount ?? 0),
  );
  const currentTypeItems = metrics?.categories ?? types.items;
  const categoryName =
    currentTypeItems.find((n) => String(n.type_id) === filters.type_id)?.name ??
    "";
  const frameOptions = metrics?.frames ?? [];
  const diagnosticsCount =
    (metrics?.quarantined_count ?? 0) + (metrics?.conflict_count ?? 0);
  const currentTypes = new Map(
    currentTypeItems.map((t) => [t.type_id, t.name]),
  );
  const currentPageItems = page.items.map((item) => ({
    ...item,
    type_name: currentTypes.get(item.type_id) ?? item.type_name,
  }));
  const exportUrl = run
    ? `${runPath(run)}/export.ndjson?${filterParams(effectiveFilters)}`
    : "";
  return (
    <div className={`app-shell mobile-${mobilePanel}`}>
      <header className="topbar">
        <a className="brand" href="/" aria-label="ASTRA 宇宙万物观测站">
          <span className="brand-mark">
            <Orbit size={27} strokeWidth={1.1} />
          </span>
          <span>
            ASTRA<small>宇宙万物观测站</small>
          </span>
        </a>
        <div className="topbar-middle">
          <span className="workspace-label">观测工作台</span>
          <span className="top-divider" />
          <div className="run-selector">
            <span className="tiny-dot" />
            <select
              aria-label="选择观测运行"
              value={run}
              onChange={(e) => setRun(e.target.value)}
              disabled={!runs.length}
            >
              {runs.length ? (
                runs.map((r) => (
                  <option key={r.test_id} value={r.test_id}>
                    {r.test_id}
                  </option>
                ))
              ) : (
                <option value="">
                  {loading.runs ? "连接观测站…" : "等待首次接入"}
                </option>
              )}
            </select>
            <ChevronDown size={13} />
          </div>
        </div>
        <div className="topbar-right">
          <span className={`connection ${connected ? "" : "offline"}`}>
            {connected ? <Wifi size={13} /> : <WifiOff size={13} />}
            <span>
              {loading.runs ? "连接中" : connected ? "系统在线" : "连接中断"}
            </span>
          </span>
          <button
            className="icon-button refresh-top"
            title="刷新观测视图"
            aria-label="刷新观测视图"
            onClick={refreshView}
          >
            <RefreshCw size={16} />
          </button>
          <button
            className="diagnostics-button"
            onClick={() => setDiagnostics(true)}
            disabled={!run}
          >
            <ShieldCheck size={15} />
            <span>接入状态</span>
            {diagnosticsCount > 0 && <i>{diagnosticsCount}</i>}
          </button>
        </div>
      </header>
      <div className="metrics-strip">
        <div className="metric primary">
          <span>已发现对象</span>
          <strong>{metrics ? displayNumber(metrics.object_count) : "—"}</strong>
          <small>当前有效对象</small>
        </div>
        <div className="metric">
          <span>
            <Activity size={12} />
            有效入库速率
          </span>
          <strong>
            {metrics ? displayNumber(metrics.rate_objects_per_second) : "—"}
            <em>个 / 秒</em>
          </strong>
        </div>
        <div className="metric">
          <span>
            <Layers3 size={12} />
            分类版本
          </span>
          <strong>
            {metrics ? String(metrics.revision).padStart(2, "0") : "—"}
            <em>REV</em>
          </strong>
        </div>
        <div className="metric">
          <span>
            <Database size={12} />
            持久化占用
          </span>
          <strong className="metric-bytes">
            {metrics ? displayBytes(metrics.database_bytes) : "—"}
          </strong>
          <small>
            {metrics
              ? `预算 ${displayBytes(metrics.storage_limit_bytes)}`
              : "等待状态"}
          </small>
        </div>
        <button
          className={`metric metric-status ${diagnosticsCount ? "has-warning" : ""}`}
          onClick={() => setDiagnostics(true)}
          disabled={!run}
        >
          <span>
            {diagnosticsCount ? <AlertCircle size={12} /> : <Check size={12} />}
            数据完整性
          </span>
          <strong>
            {metrics ? displayNumber(diagnosticsCount) : "—"}
            <em>隔离 / 冲突</em>
          </strong>
          <small>
            {metrics
              ? `${displayNumber(metrics.duplicate_count)} 次重复已去重`
              : "原始消息可靠留存"}
          </small>
        </button>
        <div className="metric metric-last">
          <span>最近接入</span>
          <strong>{metrics ? displayTime(metrics.updated_at) : "—"}</strong>
          <small>
            {metrics
              ? `${displayNumber(metrics.message_count)} 条已保存消息`
              : "等待观测信号"}
          </small>
        </div>
      </div>
      {(errors.connection || stale) && (
        <div className="connection-banner">
          <WifiOff size={14} />
          <span>
            连接暂时中断，保留最后一次成功读取的数据。{errors.connection}
          </span>
          <button onClick={() => window.location.reload()}>重新连接</button>
        </div>
      )}
      <nav className="mobile-tabs">
        <button
          className={mobilePanel === "types" ? "active" : ""}
          onClick={() => setMobilePanel("types")}
        >
          <FolderTree size={16} />
          分类
        </button>
        <button
          className={mobilePanel === "scene" ? "active" : ""}
          onClick={() => setMobilePanel("scene")}
        >
          <Orbit size={16} />
          探索
        </button>
        <button
          className={mobilePanel === "detail" ? "active" : ""}
          onClick={() => setMobilePanel("detail")}
        >
          <Scan size={16} />
          详情{selected && <span className="tiny-dot" />}
        </button>
      </nav>
      <main className="workspace">
        <div className="left-column">
          <CategoryTree
            items={currentTypeItems}
            changes={types.changes}
            selected={filters.type_id}
            onSelect={(id) => {
              setFilters((old) => ({ ...old, type_id: id }));
              if (window.innerWidth <= 760) setMobilePanel("scene");
            }}
            total={metrics?.object_count ?? 0}
            revision={metrics?.revision ?? types.revision}
            loading={loading.types}
            descendants={filters.descendants}
            onDescendants={(value) =>
              setFilters((old) => ({ ...old, descendants: value }))
            }
          />
          {errors.types && <p className="error-inline">{errors.types}</p>}
        </div>
        <div className="center-column">
          <div className="view-toolbar">
            <div className="view-label">
              <Orbit size={16} />
              <span>空间观测</span>
              <small>3D</small>
            </div>
            <div className="frame-select">
              <select
                aria-label="选择空间坐标系"
                value={frame ? frameKey(frame) : ""}
                onChange={(e) => {
                  setFrame(
                    frameOptions.find((f) => frameKey(f) === e.target.value) ??
                      null,
                  );
                  scene.current?.reset();
                }}
                disabled={!frameOptions.length}
              >
                {frameOptions.length ? (
                  frameOptions.map((f) => (
                    <option value={frameKey(f)} key={frameKey(f)}>
                      {f.frame_id} · {f.frame_kind} · {f.unit}
                    </option>
                  ))
                ) : (
                  <option value="">无坐标数据</option>
                )}
              </select>
              <ChevronDown size={13} />
            </div>
          </div>
          <div className="scene-wrap">
            <UniverseScene
              ref={scene}
              points={points}
              frame={frame}
              total={pointTotal}
              loading={loading.points}
              error={errors.points}
              selected={selected}
              onSelect={selectObject}
              hasRun={!!run}
            />
            {additions > 0 && (
              <button className="new-data" onClick={refreshView}>
                <span className="tiny-dot" />
                全站新增 {displayNumber(additions)} 个对象
                <RefreshCw size={13} />
              </button>
            )}
            {filters.type_id && (
              <div className="scene-filter">
                <span>{categoryName}</span>
                <button
                  aria-label="清除分类筛选"
                  onClick={() => setFilters((old) => ({ ...old, type_id: "" }))}
                >
                  <X size={12} />
                </button>
              </div>
            )}
          </div>
          <ObjectList
            items={currentPageItems}
            loading={loading.list}
            error={errors.list}
            selected={selected}
            onSelect={selectObject}
            nextCursor={page.next_cursor}
            page={pageIndex}
            onNext={nextPage}
            onPrevious={() => setPageIndex((v) => Math.max(0, v - 1))}
            exportUrl={exportUrl}
            search={search}
            searchMode={searchMode}
            onSearch={setSearch}
            onMode={setSearchMode}
            categoryName={categoryName}
            onClearCategory={() =>
              setFilters((old) => ({ ...old, type_id: "" }))
            }
            collapsed={collapsed}
            onCollapse={() => setCollapsed(!collapsed)}
            refreshing={loading.list}
            frameFilter={frameFilter}
            onFrameFilter={setFrameFilter}
            hasFrame={!!frame}
          />
        </div>
        <div className="right-column">
          <Inspector
            object={detail?.object ?? null}
            metadata={detail?.meta ?? null}
            typeName={
              detail
                ? (currentTypes.get(detail.object.type_id) ??
                  detail.meta.type_name)
                : ""
            }
            loading={loading.detail}
            error={errors.detail}
            canFocus={points.some((p) => p.id === selected)}
            onFocus={() => {
              scene.current?.focus(selected);
              setMobilePanel("scene");
            }}
            onClear={() => setSelected("")}
          />
        </div>
      </main>
      <footer className="statusbar">
        <span>
          <span className={`tiny-dot ${connected ? "" : "pending"}`} />
          {connected ? "实时链路已连接" : "等待重新连接"}
          <span className="status-separator">/</span>可靠保存后确认
        </span>
        <span className="status-middle">真实观测 · 独立坐标系 · 有界点云</span>
        <span>
          {metrics ? `${displayNumber(metrics.backlog)} 条待处理` : "等待接入"}
          <a href="/docs" target="_blank" rel="noreferrer">
            API
            <ArrowUpRight size={11} />
          </a>
        </span>
      </footer>
      {diagnostics && run && (
        <Diagnostics
          run={run}
          metrics={metrics}
          onClose={() => setDiagnostics(false)}
        />
      )}
    </div>
  );
}
