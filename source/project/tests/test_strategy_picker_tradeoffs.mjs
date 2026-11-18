import assert from 'node:assert/strict';
import {test} from 'node:test';
import * as picker from '../webui/web/public/strategy-picker/picker.js';

// Anonymous raw ratios from an actual two-repeat selected-goal experiment.
export function case10(){
  const run=(values)=>({targets:'a'.repeat(64),context_sha256:'b'.repeat(64),
    metrics:Object.fromEntries(['tcp','http','tls12','tls13','quic'].map((key,i)=>[key,{ok:values[i],total:[110,35,35,35,21][i]}]))});
  const baseline={id:'original',name:'Original',rank:{reason:'baseline'},sample_type:'repeated',
    runs:[run([96,22,31,28,9]),run([95,23,34,34,10])]};
  const candidate={id:'generated',recipe:'new',name:'Generated',rank:{eligible:true},sample_type:'repeated',
    runs:[run([61,13,32,32,14]),run([60,15,33,33,12])]};
  return {id:'c'.repeat(32),state:'completed',restored:true,can_apply:true,goal:'youtube,discord,instagram',
    winner:'generated:new',profiles:[baseline,candidate]};
}

test('Actual selected-goal tradeoff uses the minimum of both repeats and raw denominators',()=>{
  const j=case10(),v=picker.tradeoffComparison(j,j.profiles[1]);
  assert.equal(v.known,true);
  assert.deepEqual(v.losses,[{key:'tcp',baseline:95,candidate:60,total:110},{key:'http',baseline:22,candidate:13,total:35}]);
  for(const language of ['ru','en']){
    const text=picker.tradeoffNotice(j,j.profiles[1],language);
    assert.match(text,/TCP 95\/110 → 60\/110/);assert.match(text,/HTTP 22\/35 → 13\/35/);
    assert.doesNotMatch(text,/%/);
  }
});

test('The original profile remains the reference when a pass-through control is present',()=>{
  const j=case10(),zero=structuredClone(j.profiles[0]);zero.rank={reason:'zero_baseline'};
  for(const run of zero.runs)for(const metric of Object.values(run.metrics))metric.ok=0;
  j.profiles.splice(1,0,zero);
  assert.equal(picker.tradeoffComparison(j,j.profiles[2]).losses[0].baseline,95);
});

test('Stable or improved minima do not become an invented tradeoff from the upper range',()=>{
  const j=case10();j.profiles[1].runs=structuredClone(j.profiles[0].runs);
  j.profiles[1].runs[0].metrics.tcp.ok=96;j.profiles[1].runs[1].metrics.tcp.ok=96;
  assert.deepEqual(picker.tradeoffComparison(j,j.profiles[1]),{known:true,losses:[]});
  assert.equal(picker.tradeoffNotice(j,j.profiles[1],'ru'),'');
});

test('Incomplete, changed or malformed measurements are unknown and cannot produce Apply text',()=>{
  const changes=[j=>delete j.profiles[0].runs[0].metrics.tcp,
    j=>j.profiles[1].runs[0].metrics.tcp.ok=NaN,
    j=>j.profiles[1].runs[0].metrics.tcp.ok=Infinity,
    j=>j.profiles[1].runs[0].metrics.tcp.ok='60',
    j=>j.profiles[1].runs[0].metrics.tcp.ok=-1,
    j=>j.profiles[1].runs[0].metrics.tcp.ok=111,
    j=>j.profiles[1].runs[0].metrics.tcp.total=109,
    j=>j.profiles[1].runs[0].targets='d'.repeat(64),
    j=>delete j.profiles[1].runs[0].targets,
    j=>j.profiles[1].runs[1].context_sha256='d'.repeat(64),
    j=>j.profiles[1].runs.splice(1),
    j=>j.profiles[0].runs.splice(1)];
  for(const change of changes){
    const j=case10();change(j);
    assert.equal(picker.tradeoffComparison(j,j.profiles[1]).known,false);
    assert.match(picker.tradeoffNotice(j,j.profiles[1],'en'),/unavailable|compare/i);
    assert.equal(picker.applyDescription(j,'ru',false),null);
  }
});

test('Malformed ranges remain renderable and never show NaN or coerced strings',()=>{
  for(const change of [j=>delete j.profiles[1].runs[0].metrics.http,
    j=>j.profiles[1].runs[0].metrics.http.ok='5',
    j=>j.profiles[1].runs[1].metrics.http.total=34]){
    const j=case10();change(j);assert.deepEqual(picker.ranges(j.profiles[1].runs),[]);
  }
});

test('Malformed profile collections or run containers yield unknown comparison without crashing',()=>{
  for(const job of [null,{profiles:{}},{profiles:[]},{profiles:[null]},
    {profiles:[{rank:{reason:'baseline'},runs:{length:2}}]}]){
    assert.deepEqual(picker.tradeoffComparison(job,{runs:[{},{}]}),{known:false,losses:[]});
    assert.equal(picker.applyDescription(job,'en',false),null);
  }
});

test('All-services goal also reports individual metric declines',()=>{
  const j=case10();j.goal='all';
  assert.equal(picker.tradeoffComparison(j,j.profiles[1]).losses.length,2);
  assert.match(picker.applyDescription(j,'en',false),/TCP 95\/110 → 60\/110/);
});

test('Apply confirmation names the measured goal and repeats the visible tradeoff in both languages',()=>{
  const j=case10();
  for(const language of ['ru','en']){
    const text=picker.applyDescription(j,language,false);
    assert.match(text,/YouTube.*Discord.*Instagram/);
    assert.ok(text.includes(picker.tradeoffNotice(j,j.profiles[1],language)));
    assert.match(text,/IPv4/);
  }
  assert.match(picker.applyDescription(j,'ru',true),/без отдельного измерения/);
  assert.match(picker.applyDescription(j,'en',true),/not separately measured/);
});

test('An active, failed, stale, unverified or absent candidate has no Apply confirmation',()=>{
  const changes=[j=>j.state='running',j=>j.state='failed',j=>j.state='cancelled',
    j=>j.state='recovery_required',j=>j.restored=false,j=>j.can_apply=false,
    j=>j.winner='missing',j=>j.profiles[1].rank.eligible=false,
    j=>j.profiles[1].sample_type='exploratory'];
  for(const change of changes){const j=case10();change(j);assert.equal(picker.applyDescription(j,'en',false),null);}
});

// Execute the actual module and event listeners. Fetch stays in memory and every
// mutation is recorded; no router, external network or production code injection.
async function withRenderer(check){
  const previous={document:globalThis.document,window:globalThis.window,fetch:globalThis.fetch};
  const nodes=new Map(),windowEvents=new Map(),calls=[],requests=[];
  function element(){return {hidden:false,disabled:false,checked:false,value:'synthesis',childNodes:[],textContent:'',
    classList:{toggle(){}},listeners:new Map(),append(v){this.childNodes.push(v);},replaceChildren(){this.childNodes=[];},
    addEventListener(type,fn){this.listeners.set(type,fn);}};}
  const document={hidden:false,documentElement:{lang:'ru'},addEventListener(){},removeEventListener(){},
    getElementById(id){if(!nodes.has(id))nodes.set(id,element());return nodes.get(id);},createElement:element};
  let response={job:{...case10(),search:'synthesis',skipped:[]},active:false,detector:{installed:true}};
  document.getElementById('confirmation').hidden=true;
  globalThis.document=document;globalThis.window={addEventListener(type,fn){windowEvents.set(type,fn);}};
  globalThis.fetch=async(url,options)=>{const cmd=options.body.get('cmd');calls.push(cmd);requests.push(Object.fromEntries(options.body));
    return {ok:true,status:200,json:async()=>structuredClone(cmd==='status'?{csrf_token:'fixture'}:response)};};
  const flush=()=>new Promise(resolve=>setImmediate(resolve));
  const click=async id=>{nodes.get(id).listeners.get('click')();await flush();};
  try{
    await import('../webui/web/public/strategy-picker/picker.js?renderer='+Math.random());await flush();
    await check({nodes,calls,requests,click,async update(job){response={...response,job};await click('refresh');}});
  }finally{
    windowEvents.get('pagehide')?.();
    for(const [key,value] of Object.entries(previous)){if(value===undefined)delete globalThis[key];else globalThis[key]=value;}
  }
}

test('Repeated pass-through improvement remains visible when the generated strategy loses to the original',async()=>{
  await withRenderer(async ui=>{
    // Anonymous outcome of the real joint experiment: the two comparisons differ.
    const job={...case10(),search:'synthesis',skipped:[],can_apply:false,can_export:false,
      generation:{from_zero:{eligible:true,gain:7},versus_current:{eligible:false,reason:'youtube_regression'},verified:false}};
    await ui.update(job);
    assert.match(ui.nodes.get('generation').textContent,/относительно пустой основы подтверждён повторными измерениями/);
    assert.match(ui.nodes.get('generation').textContent,/исходная стратегия сохранена: преимущества над ней не подтверждены/);
    assert.equal(ui.nodes.get('apply').hidden,true);assert.equal(ui.nodes.get('export').hidden,true);
    await ui.click('language');
    assert.match(ui.nodes.get('generation').textContent,/confirmed improvement for the selected goal over pass-through/);
    assert.match(ui.nodes.get('generation').textContent,/original was retained: improvement over it was not confirmed/);
    assert.equal(ui.nodes.get('apply').hidden,true);assert.equal(ui.nodes.get('export').hidden,true);
    assert.equal(ui.calls.includes('pickerapply'),false);
  });
});

test('Missing or non-boolean pass-through evidence cannot acquire an improvement claim from overall verification',async()=>{
  for(const from_zero of [undefined,null,{}, {eligible:false},{eligible:'true'},{eligible:1}])await withRenderer(async ui=>{
    const job={...case10(),search:'synthesis',skipped:[],generation:{from_zero,versus_current:{eligible:true},verified:true}};
    await ui.update(job);assert.match(ui.nodes.get('generation').textContent,/пока не подтверждён/);
    await ui.click('language');assert.match(ui.nodes.get('generation').textContent,/did not confirm improvement over pass-through/);
  });
});

test('Improvement over the original requires both its own comparison and overall verification',async()=>{
  for(const [verified,eligible,confirmed] of [[true,true,true],[false,true,false],['true',true,false],[true,'true',false],[true,false,false]])await withRenderer(async ui=>{
    const job={...case10(),search:'synthesis',skipped:[],generation:{from_zero:{eligible:true},versus_current:{eligible},verified}};
    await ui.update(job);
    assert.equal(ui.nodes.get('generation').textContent.includes('Подтверждено улучшение по выбранной цели относительно исходной стратегии.'),confirmed);
    await ui.click('language');
    assert.equal(ui.nodes.get('generation').textContent.includes('It also improved the selected goal compared with the original strategy.'),confirmed);
  });
});

test('A pending Apply cannot survive status, job, winner, goal, warning or state changes',async()=>{
  const changes=[j=>j.can_apply=false,j=>j.id='d'.repeat(32),j=>j.winner='missing',
    j=>j.state='failed',j=>j.state='cancelled',j=>j.goal='youtube',
    j=>j.profiles[1].runs[1].metrics.tcp.ok=59];
  for(const change of changes)await withRenderer(async ui=>{
    assert.equal(ui.nodes.get('apply').hidden,false);await ui.click('apply');
    assert.equal(ui.nodes.get('confirmation').hidden,false);
    const job={...case10(),search:'synthesis',skipped:[]};change(job);await ui.update(job);
    assert.equal(ui.nodes.get('confirmation').hidden,true,'changed report must invalidate confirmation');
    await ui.click('confirm-submit');assert.equal(ui.calls.includes('pickerapply'),false);
  });
});

test('Malformed refreshed reports clear previous recommendation and pending Apply without throwing',async()=>{
  for(const profiles of [null,{},[null],[...case10().profiles,null]])await withRenderer(async ui=>{
    await ui.click('apply');const job={...case10(),search:'synthesis',skipped:[],profiles};await ui.update(job);
    assert.equal(ui.nodes.get('apply').hidden,true);assert.equal(ui.nodes.get('confirmation').hidden,true);
    assert.match(ui.nodes.get('tradeoffs').textContent,/сопоставить|недоступ/);
    assert.equal(ui.nodes.get('results-section').hidden,false,'unknown comparison notice must stay visible');
    assert.equal(ui.nodes.get('generation').textContent,'');
    assert.equal(ui.nodes.get('winner').textContent.includes('Generated'),false);
    assert.doesNotMatch(ui.nodes.get('error').textContent,/TypeError|Cannot read/);
    await ui.click('confirm-submit');assert.equal(ui.calls.includes('pickerapply'),false);
  });
});


test('An unchanged valid confirmation sends one Apply for the displayed job and tracker choice',async()=>{
  await withRenderer(async ui=>{
    await ui.click('apply');assert.match(ui.nodes.get('confirmation-text').textContent,/TCP 95\/110 → 60\/110/);
    await ui.click('confirm-submit');
    const sent=ui.requests.filter(r=>r.cmd==='pickerapply');
    assert.equal(sent.length,1);assert.equal(sent[0].id,'c'.repeat(32));assert.equal(sent[0].torrent_sites,'0');
    assert.equal(ui.nodes.get('confirmation').hidden,true);
  });
});
