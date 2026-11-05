import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import {
  Compass,
  Focus,
  Minus,
  Plus,
  RotateCcw,
  Scan,
  MousePointer2,
} from "lucide-react";
import { displayNumber, typeColor } from "../api";
import { createNebula } from "../nebula";
import { starLayout, STAR_PALETTE } from "../starLayout";
import type { Point, Frame } from "../types";
export interface SceneHandle {
  focus: (id: string) => void;
  reset: () => void;
}
interface Props {
  points: Point[];
  frame: Frame | null;
  total: number;
  loading: boolean;
  error: string;
  selected: string;
  onSelect: (id: string) => void;
  onFocus: () => void;
  onFocusChange: (id: string) => void;
  hasRun: boolean;
}
interface Runtime {
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  renderer: THREE.WebGLRenderer;
  controls: OrbitControls;
  data: THREE.Points;
  ring: THREE.Sprite;
  locations: Map<string, THREE.Vector3>;
  focusTarget: THREE.Vector3 | null;
  focusCamera: THREE.Vector3 | null;
  homeTarget: THREE.Vector3;
  homeCamera: THREE.Vector3;
  points: Point[];
  onSelect: (id: string) => void;
}
// Display positions use the packed layout; shader animation affects light only.
const vertexShader = `
attribute vec3 pointColor; attribute float starSeed;
uniform float pixelRatio; uniform float time;
varying vec3 vColor; varying float vLight;
void main(){
 vColor=pointColor;
 vec4 mv=modelViewMatrix*vec4(position,1.0);
 gl_Position=projectionMatrix*mv;
 gl_PointSize=clamp((260.0+starSeed*360.0)/max(1.0,-mv.z),2.0,40.0)*pixelRatio;
 vLight=(0.65+starSeed*0.35)*(0.94+0.06*sin(time*0.6+starSeed*71.0));
}`;
const fragmentShader = `
varying vec3 vColor; varying float vLight;
void main(){
 vec2 p=gl_PointCoord*2.0-1.0; float r=length(p);
 if(r>1.0)discard;
 float core=exp(-r*r*160.0);
 float corona=exp(-r*r*28.0)*0.48;
 float glow=exp(-r*r*5.0)*0.12;
 float rays=(exp(-abs(p.x)*100.0)+exp(-abs(p.y)*100.0))*exp(-r*9.0)*0.10;
 float light=(core+corona+glow+rays)*(1.0-smoothstep(0.7,1.0,r))*vLight;
 gl_FragColor=vec4(mix(vColor,vec3(1.0),core*0.45),light);
}`;
function makeRing() {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 128;
  const ctx = canvas.getContext("2d")!;
  const glow = ctx.createRadialGradient(64, 64, 2, 64, 64, 64);
  glow.addColorStop(0, "rgba(111,245,212,.65)");
  glow.addColorStop(0.25, "rgba(111,245,212,.05)");
  glow.addColorStop(1, "rgba(111,245,212,0)");
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, 128, 128);
  ctx.strokeStyle = "rgba(142,255,224,.95)";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.arc(64, 64, 35, 0, Math.PI * 2);
  ctx.stroke();
  for (const [x, y] of [
    [64, 19],
    [64, 109],
    [19, 64],
    [109, 64],
  ]) {
    ctx.beginPath();
    ctx.moveTo(x + (x === 64 ? 0 : -5), y + (y === 64 ? 0 : -5));
    ctx.lineTo(x + (x === 64 ? 0 : 5), y + (y === 64 ? 0 : 5));
    ctx.stroke();
  }
  return new THREE.CanvasTexture(canvas);
}
const UniverseScene = forwardRef<SceneHandle, Props>(function UniverseScene(
  { points, frame, total, loading, error, selected, onSelect, onFocus, onFocusChange, hasRun },
  ref,
) {
  const mount = useRef<HTMLDivElement>(null);
  const runtime = useRef<Runtime | null>(null);
  const [webglError, setWebglError] = useState("");
  const [fps, setFps] = useState<number | null>(null);
  const [overview, setOverview] = useState(false);
  const [focusedId, setFocusedId] = useState("");
  const savedView = useRef<{camera: THREE.Vector3; target: THREE.Vector3; id: string} | null>(null);
  const [hover, setHover] = useState<Point | null>(null);
  const focus = (id: string) => {
    const rt = runtime.current;
    const target = rt?.locations.get(id);
    if (!rt || !target) return;
    if (savedView.current?.id === id) {
      rt.focusCamera = savedView.current.camera.clone();
      rt.focusTarget = savedView.current.target.clone();
      savedView.current = null;
      setFocusedId(""); onFocusChange("");
      return;
    }
    if (!savedView.current) savedView.current = {camera: rt.camera.position.clone(), target: rt.controls.target.clone(), id};
    else savedView.current.id = id;
    setFocusedId(id); onFocusChange(id);
    rt.focusTarget = target.clone();
    const direction = rt.camera.position
      .clone()
      .sub(rt.controls.target)
      .normalize();
    rt.focusCamera = target.clone().add(direction.multiplyScalar(Math.max(0.5, rt.homeCamera.distanceTo(rt.homeTarget) * 0.10)));
  };
  const reset = () => {
    const rt = runtime.current;
    if (!rt) return;
    rt.focusTarget = rt.homeTarget.clone();
    rt.focusCamera = rt.homeCamera.clone();
    setOverview(false);
    savedView.current = null; setFocusedId(""); onFocusChange("");
  };
  useImperativeHandle(ref, () => ({ focus, reset }), [onFocusChange]);
  useEffect(() => {
    if (!mount.current) return;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: true,
        powerPreference: "high-performance",
      });
    } catch {
      setWebglError("当前浏览器无法开启 WebGL。对象目录与详情仍可使用。");
      return;
    }
    const node = mount.current;
    const scene = new THREE.Scene();
    const nebula = createNebula();
    scene.add(nebula.mesh);
    const camera = new THREE.PerspectiveCamera(48, 1, 0.1, 1500);
    camera.position.set(18, 9, 82);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.6));
    renderer.setClearColor(0x070b12, 0);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.domElement.setAttribute(
      "aria-label",
      "同一坐标系中的真实对象点云。拖动旋转，滚轮缩放，点击选择。",
    );
    renderer.domElement.setAttribute("role", "img");
    node.appendChild(renderer.domElement);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.07;
    controls.minDistance = 0.15;
    controls.maxDistance = 400;
    controls.rotateSpeed = 0.5;
    controls.zoomSpeed = 0.8;
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute([], 3));
    geometry.setAttribute(
      "pointColor",
      new THREE.Float32BufferAttribute([], 3),
    );
    const material = new THREE.ShaderMaterial({
      vertexShader,
      fragmentShader,
      uniforms: { pixelRatio: { value: renderer.getPixelRatio() }, time: { value: 0 } },
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    const data = new THREE.Points(geometry, material);
    scene.add(data);
    let seed = 42;
    const rnd = () => {
      seed = (seed * 1664525 + 1013904223) >>> 0;
      return seed / 4294967296;
    };
    const starVertices = [];
    const starColors = [];
    const starSeeds = [];
    for (let i = 0; i < 2600; i++) {
      const theta = rnd() * Math.PI * 2;
      const phi = Math.acos(2 * rnd() - 1);
      const radius = 420 + rnd() * 150;
      starVertices.push(
        radius * Math.sin(phi) * Math.cos(theta),
        radius * Math.cos(phi),
        radius * Math.sin(phi) * Math.sin(theta),
      );
      const c = new THREE.Color().setHSL(
        0.58 + rnd() * 0.12,
        0.2,
        0.25 + rnd() * 0.3,
      );
      starColors.push(c.r, c.g, c.b);
      starSeeds.push(rnd());
    }
    const starGeo = new THREE.BufferGeometry();
    starGeo.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(starVertices, 3),
    );
    starGeo.setAttribute(
      "pointColor",
      new THREE.Float32BufferAttribute(starColors, 3),
    );
    starGeo.setAttribute("starSeed", new THREE.Float32BufferAttribute(starSeeds, 1));
    const starMat = new THREE.ShaderMaterial({
      vertexShader, fragmentShader,
      uniforms: { pixelRatio: { value: renderer.getPixelRatio() }, time: { value: 0 } },
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    });
    // Decorative sky is separate from selectable observations.
    scene.add(new THREE.Points(starGeo, starMat));
    const ringTexture = makeRing();
    const ring = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: ringTexture,
        transparent: true,
        depthTest: false,
        depthWrite: false,
      }),
    );
    ring.scale.set(11, 11, 1);
    ring.visible = false;
    scene.add(ring);
    const rt: Runtime = {
      scene,
      camera,
      renderer,
      controls,
      data,
      ring,
      locations: new Map(),
      focusTarget: null,
      focusCamera: null,
      homeTarget: new THREE.Vector3(),
      homeCamera: new THREE.Vector3(18, 9, 82),
      points: [],
      onSelect,
    };
    runtime.current = rt;
    let visible = true;
    const resize = new ResizeObserver(() => {
      const { width, height } = node.getBoundingClientRect();
      visible = width > 0 && height > 0;
      if (!visible) return;
      renderer.setSize(width, height);
      camera.aspect = width / height;
      nebula.material.uniforms.aspect.value = camera.aspect;
      camera.updateProjectionMatrix();
    });
    resize.observe(node);
    let downX = 0, downY = 0;
    const projected = new THREE.Vector3();
    const hit = (event: PointerEvent) => {
      const box = renderer.domElement.getBoundingClientRect();
      let best: Point | undefined;
      let distance = 9;
      for (const point of rt.points) {
        const location = rt.locations.get(point.id);
        if (!location) continue;
        projected.copy(location).project(camera);
        if (projected.z < -1 || projected.z > 1) continue;
        const dx = (projected.x + 1) * box.width / 2 - (event.clientX - box.left);
        const dy = (1 - projected.y) * box.height / 2 - (event.clientY - box.top);
        const d = Math.hypot(dx, dy);
        if (d < distance) { distance = d; best = point; }
      }
      return best;
    };
    const down = (event: PointerEvent) => {
      downX = event.clientX;
      downY = event.clientY;
    };
    const up = (event: PointerEvent) => {
      if (Math.hypot(event.clientX - downX, event.clientY - downY) > 6) return;
      const object = hit(event);
      if (object) rt.onSelect(object.id);
    };
    let lastHover = 0;
    const move = (event: PointerEvent) => {
      if (event.buttons || performance.now() - lastHover < 80) return;
      lastHover = performance.now();
      const point = hit(event);
      setHover(point ?? null);
      renderer.domElement.style.cursor = point ? "pointer" : "grab";
    };
    const leave = () => setHover(null);
    renderer.domElement.addEventListener("pointerdown", down);
    renderer.domElement.addEventListener("pointerup", up);
    renderer.domElement.addEventListener("pointermove", move);
    renderer.domElement.addEventListener("pointerleave", leave);
    const contextLost = (e: Event) => {
      e.preventDefault();
      setWebglError("三维渲染暂时中断，请刷新页面。目录与导出继续可用。");
    };
    renderer.domElement.addEventListener("webglcontextlost", contextLost);
    let animation = 0,
      count = 0,
      last = performance.now();
    const reduced = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    const animate = () => {
      animation = requestAnimationFrame(animate);
      if (document.hidden || !visible) {
        last = performance.now();
        count = 0;
        return;
      }
      if (rt.focusTarget && rt.focusCamera) {
        controls.target.lerp(rt.focusTarget, reduced ? 1 : 0.095);
        camera.position.lerp(rt.focusCamera, reduced ? 1 : 0.095);
        if (camera.position.distanceTo(rt.focusCamera) < 0.05) {
          rt.focusTarget = null;
          rt.focusCamera = null;
        }
      }
      controls.update();
      if (ring.visible) {
        const distance = camera.position.distanceTo(ring.position);
        const size = Math.max(0.08, distance * 0.078);
        ring.scale.set(size, size, 1);
      }
      material.uniforms.time.value = reduced ? 0 : performance.now() / 1000;
      starMat.uniforms.time.value = material.uniforms.time.value;
      nebula.material.uniforms.time.value = material.uniforms.time.value;
      renderer.render(scene, camera);
      count++;
      const now = performance.now();
      if (now - last >= 1000) {
        setFps(Math.round((count * 1000) / (now - last)));
        count = 0;
        last = now;
      }
    };
    animate();
    return () => {
      cancelAnimationFrame(animation);
      resize.disconnect();
      controls.dispose();
      geometry.dispose();
      material.dispose();
      starGeo.dispose();
      starMat.dispose();
      nebula.dispose();
      ringTexture.dispose();
      (ring.material as THREE.Material).dispose();
      renderer.dispose();
      renderer.domElement.remove();
      runtime.current = null;
    };
  }, []);
  useEffect(() => {
    if (runtime.current) runtime.current.onSelect = onSelect;
  }, [onSelect]);
  useEffect(() => {
    const rt = runtime.current;
    if (!rt) return;
    const previousFirst = rt.points[0]?.id;
    rt.points = points;
    rt.locations.clear();
    const positions = starLayout(points, true);
    const vertices = new Float32Array(points.length * 3);
    const colors = new Float32Array(points.length * 3);
    const seeds = new Float32Array(points.length);
    for (let i = 0; i < points.length; i++) {
      const p = points[i];
      const vector = new THREE.Vector3(...positions[i]);
      vertices.set([vector.x, vector.y, vector.z], i * 3);
      rt.locations.set(p.id, vector);
      let hash = 2166136261;
      for (const char of p.id) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619);
      seeds[i] = (hash >>> 0) / 4294967295;
      // Display tint only: no inferred physical temperature or luminosity.
      const color = new THREE.Color(STAR_PALETTE[(hash >>> 8) % STAR_PALETTE.length]);
      colors.set([color.r, color.g, color.b], i * 3);
    }
    rt.data.geometry.setAttribute(
      "position",
      new THREE.BufferAttribute(vertices, 3),
    );
    rt.data.geometry.setAttribute(
      "pointColor",
      new THREE.BufferAttribute(colors, 3),
    );
    rt.data.geometry.setAttribute("starSeed", new THREE.BufferAttribute(seeds, 1));
    rt.data.geometry.computeBoundingSphere();
    if (points.length && previousFirst !== points[0].id) {
      rt.homeTarget.set(0,0,0);
      rt.homeCamera.copy(new THREE.Vector3(0.18,0.1,1).normalize().multiplyScalar(25));
      rt.camera.position.copy(rt.homeCamera);
      rt.controls.target.copy(rt.homeTarget);
      rt.controls.update();
      rt.focusCamera = null; rt.focusTarget = null;
      savedView.current = null; setFocusedId(""); onFocusChange("");
      setOverview(false);
    }
    setHover(null);
  }, [points, onFocusChange]);
  useEffect(() => {
    const rt = runtime.current;
    if (!rt) return;
    const location = rt.locations.get(selected);
    rt.ring.visible = !!location;
    if (location) rt.ring.position.copy(location);
  }, [selected, points]);
  const zoom = (factor: number) => {
    const rt = runtime.current;
    if (!rt) return;
    const vector = rt.camera.position
      .clone()
      .sub(rt.controls.target)
      .multiplyScalar(factor);
    rt.camera.position.copy(rt.controls.target.clone().add(vector));
    rt.controls.update();
  };
  return (
    <div className="universe-scene">
      <div className="nebula" aria-hidden="true" />
      <div className="scene-canvas" ref={mount} />
      <div className="scene-topline">
        <span>
          <span className="tiny-dot" />
          {frame ? `${frame.frame_id} / ${frame.unit}` : "等待坐标系"}
        </span>
        {fps !== null && (
          <span className="fps" title="浏览器实时渲染帧率">
            {fps} FPS
          </span>
        )}
      </div>
      {hover && (
        <div className="point-tooltip">
          <span style={{ background: typeColor(hover.type_id) }} />
          <div>
            <strong>{hover.name}</strong>
            <small>点击查看完整观测</small>
          </div>
        </div>
      )}
      <div className="scene-title">
        <div className="scene-title-line" />
        <h1>宇宙万物观测站</h1>
        <p>从真实观测，探索不断变化的世界。</p>
      </div>
      <div className="scene-controls">
        <button aria-label={overview ? "进入局部星空" : "查看坐标全景"} title={overview ? "进入局部星空" : "查看坐标全景"} onClick={() => {
          const rt = runtime.current;
          if (!rt) return;
          if (overview) reset();
          else { rt.focusTarget = new THREE.Vector3(); rt.focusCamera = new THREE.Vector3(12,8,48); savedView.current=null; setFocusedId(""); onFocusChange(""); setOverview(true); }
        }}><Compass size={16}/></button>
        <button aria-label="放大" onClick={() => zoom(0.8)}>
          <Plus size={17} />
        </button>
        <button aria-label="缩小" onClick={() => zoom(1.25)}>
          <Minus size={17} />
        </button>
        <span />
        <button aria-label="重置视角" onClick={reset}>
          <RotateCcw size={15} />
        </button>
        <button
          aria-label={focusedId === selected && selected ? "回到原处" : "聚焦选中对象"}
          disabled={!selected || !points.some((p) => p.id === selected)}
          onClick={() => { focus(selected); onFocus(); }}
        >
          <Focus size={16} />
        </button>
      </div>
      <div className="scene-bottom">
        <span>
          <Compass size={14} />
          {frame ? `${frame.frame_kind} · 原始单位 ${frame.unit}` : "空间视图"}
          <small>展示布局</small>
        </span>
        <span>
          {overview ? "全景" : "局部星空"} · 前 {displayNumber(points.length)} / {displayNumber(total)}{" "}
          个匹配坐标对象
        </span>
      </div>
      <div className="scene-hint">
        <MousePointer2 size={12} />
        拖动旋转 · 滚轮缩放 · 点选探索<span>背景星空为装饰</span>
      </div>
      {(webglError || error) && (
        <div className="scene-message error-inline">
          <Scan size={24} />
          <p>{webglError || error}</p>
        </div>
      )}
      {!webglError &&
        !error &&
        (!hasRun || (!loading && points.length === 0)) && (
          <div className="scene-message">
            <div className="empty-orbit">
              <Scan size={25} />
            </div>
            <h3>
              {!hasRun
                ? "第一束信号，即将到来"
                : !frame
                  ? "这片世界尚无空间坐标"
                  : "当前范围暂无坐标点"}
            </h3>
            <p>
              {!hasRun
                ? "启动发生器，将观测发送到 /ingest。"
                : !frame
                  ? "所有对象仍可通过下方目录探索。"
                  : "试试其他分类、坐标系或搜索条件。"}
            </p>
          </div>
        )}
      {loading && (
        <div className="scene-loading">
          <span className="spinner" />
          读取真实观测点…
        </div>
      )}
    </div>
  );
});
export default UniverseScene;
