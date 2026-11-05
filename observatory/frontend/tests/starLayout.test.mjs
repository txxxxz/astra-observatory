import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import ts from 'typescript';
const source = fs.readFileSync(new URL('../src/starLayout.ts',import.meta.url),'utf8');
const js = ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {starLayout,fillViewport} = await import('data:text/javascript;base64,'+Buffer.from(js).toString('base64'));
for(const count of [599,3000]) test(`${count} observations fill wide and narrow viewports without clipping or source mutations`,()=>{
  const data=Array.from({length:count},(_,i)=>({id:`star-${i}`,x:(i%4)*1000+Math.sin(i*7)*20,y:(i%3)*200+Math.cos(i*11)*12,z:Math.sin(i*13)*4}));
  const original=JSON.stringify(data); const packed=starLayout(data,true);
  for(const aspect of [390/844,1280/800,1920/900]){
    const placed=fillViewport(packed,data.map(p=>p.id),aspect);
    const ndc=placed.map(p=>[p[0]/((25-p[2])*Math.tan(Math.PI*24/180)*aspect),p[1]/((25-p[2])*Math.tan(Math.PI*24/180))]);
    assert.ok(placed.flat().every(Number.isFinite));
    assert.ok(ndc.flat().every(v=>Math.abs(v)<=0.981));
    for(const axis of [0,1]){
      assert.ok(Math.min(...ndc.map(p=>p[axis])) < -0.95);
      assert.ok(Math.max(...ndc.map(p=>p[axis])) > 0.95);
      assert.ok(ndc.filter(p=>p[axis]<-0.5).length>count*0.15);
      assert.ok(ndc.filter(p=>p[axis]>0.5).length>count*0.15);
    }
  }
  assert.equal(JSON.stringify(data),original);
});
test('empty and single-object layouts remain finite',()=>{
  assert.deepEqual(fillViewport([],[],1),[]);
  assert.deepEqual(fillViewport([[0,0,0]],['only'],2),[[0,0,0]]);
});
