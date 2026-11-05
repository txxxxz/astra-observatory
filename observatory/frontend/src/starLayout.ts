import type { Point } from './types';
export type XYZ = [number, number, number];

/** Display-only layout. Never mutates observations or their exported coordinates. */
export function starLayout(points: Point[], enhanced: boolean): XYZ[] {
  if (!points.length) return [];
  const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
  for (const p of points) [p.x,p.y,p.z].forEach((v,k) => {min[k]=Math.min(min[k],v);max[k]=Math.max(max[k],v);});
  const scale = 110 / Math.max(1, ...max.map((v,k) => v-min[k]));
  const base: XYZ[] = points.map(p => [p.x,p.y,p.z].map((v,k) => (v-(min[k]+max[k])/2)*scale) as XYZ);
  if (!enhanced) return base;

  // Spatial connected components, not semantic categories. Only dense groups are
  // packed; isolated observations remain visible in the surrounding volume.
  const parent = base.map((_,i) => i);
  const root = (i: number): number => {while(parent[i]!==i){parent[i]=parent[parent[i]];i=parent[i];}return i;};
  const radius = 1.3;
  const cells = new Map<string, number[]>();
  base.forEach((p,i) => {
    const c = p.map(v => Math.floor(v/radius));
    for(let x=-1;x<=1;x++) for(let y=-1;y<=1;y++) for(let z=-1;z<=1;z++) {
      for(const j of cells.get(`${c[0]+x},${c[1]+y},${c[2]+z}`) ?? []) {
        if(p.reduce((d,v,k)=>d+(v-base[j][k])**2,0)<radius**2) parent[root(i)]=root(j);
      }
    }
    const key=c.join(','); const bucket=cells.get(key)??[];bucket.push(i);cells.set(key,bucket);
  });
  const groups = new Map<number, {sum:number[];count:number}>();
  base.forEach((p,i)=>{const r=root(i);const g=groups.get(r)??{sum:[0,0,0],count:0};p.forEach((v,k)=>g.sum[k]+=v);g.count++;groups.set(r,g);});
  return base.map((p,i)=>{
    const g=groups.get(root(i))!;
    return p.map((v,k)=>{
      const center=g.sum[k]/g.count;
      const packed=g.count>=24 ? center*0.12+(v-center)*2.8 : v*0.24;
      return packed*(k===2?8:1);
    }) as XYZ;
  });
}

// Stable, low-saturation display palette; does not infer physical temperature.
export const STAR_PALETTE = ['#ead2a8', '#e5b4ac', '#abc7ef', '#e2ded3', '#bcd6e8'];

/** Spread the display projection across the viewport, retaining depth and identity.
 * Rank blending reduces empty margins caused by dense groups/outliers. These are
 * display coordinates only; API/detail/export continue using source XYZ.
 */
export function fillViewport(positions: XYZ[], ids: string[], aspect: number): XYZ[] {
  if (!positions.length) return [];
  const distance = 25;
  const tanHalfFov = Math.tan(24 * Math.PI / 180);
  const depth = positions.map(p => 8 * Math.tanh(p[2] / 10));
  const axes = [0, 1].map(axis => {
    const values = positions.map((p,i) => p[axis] / (distance-depth[i]));
    // Independent stable tie order per axis avoids turning coincident objects
    // into artificial diagonal lines when their quantiles are spread apart.
    const tie = ids.map(id => {
      let h = 2166136261 ^ (axis * 0x9e3779b9);
      for (const char of id) h = Math.imul(h ^ char.charCodeAt(0), 16777619);
      h = Math.imul(h ^ (h >>> 16), 0x85ebca6b);
      h = Math.imul(h ^ (h >>> 13), 0xc2b2ae35);
      return (h ^ (h >>> 16)) >>> 0;
    });
    const ordered = values.map((_,i) => i).sort((a,b) => values[a]-values[b] || tie[a]-tie[b] || ids[a].localeCompare(ids[b]));
    const result = new Array<number>(positions.length);
    const min = values[ordered[0]], max = values[ordered[ordered.length-1]];
    ordered.forEach((i,rank) => {
      const quantile = positions.length===1 ? 0 : 2*(rank+0.5)/positions.length-1;
      const linear = max>min ? 2*(values[i]-min)/(max-min)-1 : 0;
      result[i] = (quantile*0.88+linear*0.12)*0.98;
    });
    return result;
  });
  return positions.map((_,i) => {
    const halfHeight=(distance-depth[i])*tanHalfFov;
    return [axes[0][i]*halfHeight*aspect,axes[1][i]*halfHeight,depth[i]];
  });
}
