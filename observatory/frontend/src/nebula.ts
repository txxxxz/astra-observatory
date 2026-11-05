import * as THREE from 'three';

/** Decorative dust, rendered in the existing WebGL context with one draw call. */
export function createNebula() {
  const size = 128;
  const bytes = new Uint8Array(size * size * 4);
  let seed = 71821;
  for (let i=0;i<bytes.length;i+=4) {
    seed = (Math.imul(seed,1664525)+1013904223)>>>0;
    bytes[i]=bytes[i+1]=bytes[i+2]=seed>>>24; bytes[i+3]=255;
  }
  const noise = new THREE.DataTexture(bytes,size,size,THREE.RGBAFormat);
  noise.wrapS=noise.wrapT=THREE.RepeatWrapping;
  noise.magFilter=noise.minFilter=THREE.LinearFilter;
  noise.needsUpdate=true;
  const material=new THREE.ShaderMaterial({
    depthTest:false, depthWrite:false, transparent:true,
    uniforms:{noiseMap:{value:noise}, time:{value:0}, aspect:{value:1}},
    vertexShader:`varying vec2 uvSky; void main(){uvSky=uv;gl_Position=vec4(position.xy,0.999,1.0);}`,
    fragmentShader:`
      uniform sampler2D noiseMap; uniform float time; uniform float aspect; varying vec2 uvSky;
      float cloud(vec2 p){
        float n=0.0; float a=0.56;
        for(int i=0;i<4;i++){vec2 grid=p*128.0;vec2 f=fract(grid);f=f*f*(3.0-2.0*f);n+=a*texture2D(noiseMap,(floor(grid)+f+0.5)/128.0).r;p=p*2.07+0.13;a*=0.5;}
        return n;
      }
      void main(){
        vec2 p=uvSky-0.5;p.x*=aspect;
        vec2 drift=vec2(time*0.001,-time*0.0006);
        float warp=cloud(p*0.025+drift);
        float n=cloud(p*0.035+vec2(warp*0.008)+drift);
        float band=exp(-pow((p.y-p.x*0.32+0.10+(warp-0.5)*0.15)*2.8,2.0));
        float dust=smoothstep(0.20,0.85,n);
        float wisps=smoothstep(0.4,0.75,cloud(p*0.06+vec2(0.42,0.17)+drift));
        vec3 blue=vec3(0.12,0.24,0.34), plum=vec3(0.30,0.15,0.27);
        vec3 color=mix(blue,plum,smoothstep(-0.65,0.65,p.x+warp-0.5));
        color*=dust*band*0.60;
        color+=vec3(0.22,0.19,0.14)*wisps*band*0.09;
        // Transparent edges retain the deep black sky around the dust lane.
        gl_FragColor=vec4(color,0.88);
      }`,
  });
  const geometry=new THREE.PlaneGeometry(2,2);
  const mesh=new THREE.Mesh(geometry,material);
  mesh.frustumCulled=false; mesh.renderOrder=-100;
  return {mesh,material,dispose(){noise.dispose();material.dispose();geometry.dispose();}};
}
