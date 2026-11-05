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
