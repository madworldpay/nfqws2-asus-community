import assert from 'node:assert/strict';
import {test} from 'node:test';
import * as picker from '../webui/web/public/strategy-picker/picker.js';

test('Result numbers belong to their round and make repeat-check titles distinct',()=>{
  const j=case10();
  const cards=[{round:1,number:27,profile:j.profiles[0]},{round:2,number:1,profile:j.profiles[1]}];
  assert.equal(picker.resultCardTitle(cards[0],'ru'),'1-27 Original');
  assert.equal(picker.resultCardTitle(cards[1],'en'),'2-1 Generated');
  const retested={...cards[0],profile:{...cards[0].profile,name:'Лучшие варианты · повторная проверка'}};
  assert.equal(picker.resultCardTitle(retested,'ru'),'1-27 Вариант · повторная проверка');
});

test('A complete ratio is highlighted only when every measured result succeeded',()=>{
  for(const total of [1,2,3,37])assert.equal(picker.isFullRatio({low:total,high:total,total}),true);
  assert.equal(picker.isFullRatio({low:1,high:2,total:2}),false);
  assert.equal(picker.isFullRatio({low:2,high:2,total:3}),false);
  assert.equal(picker.isFullRatio({low:0,high:0,total:0}),false);
});

test('A result card may apply only its own current job measurement',()=>{
  const j=case10(),profile=j.profiles[1],id='d'.repeat(32),other='e'.repeat(32);
  const known=[{id,round:2,name:profile.name,sample_type:'repeated',document_available:true},
    {id:other,round:1,name:profile.name,sample_type:'repeated',document_available:true}];
  const card={id,number:1,profile,can_export:true};
  const report={id:j.id,round:2,cards:[card]};
  assert.deepEqual(picker.savedResultCards(report,j.id,2,known),[{...card,round:2}]);
  for(const invalid of [{...report,id:other},{...report,round:1},
    {...report,cards:[{...card,id:other}]},{...report,cards:[{...card,number:2}]},
    {...report,cards:[card,{...card,number:2}]}]){
    assert.equal(picker.savedResultCards(invalid,j.id,2,known),null);
  }
  const unsealed=known.map(item=>({...item,document_available:false}));
  assert.equal(picker.savedResultCards(report,j.id,2,unsealed)?.[0].can_export,false);
});

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
    setAttribute(name,value){this[name]=value;},addEventListener(type,fn){this.listeners.set(type,fn);}};}
  const document={hidden:false,documentElement:{lang:'ru'},addEventListener(){},removeEventListener(){},
    getElementById(id){if(!nodes.has(id))nodes.set(id,element());return nodes.get(id);},createElement:element};
  let response={job:{...case10(),search:'synthesis',skipped:[]},active:false,detector:{installed:true}},reports={};
  document.getElementById('confirmation').hidden=true;
  globalThis.document=document;globalThis.window={addEventListener(type,fn){windowEvents.set(type,fn);}};
  globalThis.fetch=async(url,options)=>{const cmd=options.body.get('cmd');calls.push(cmd);requests.push(Object.fromEntries(options.body));
    return {ok:true,status:200,json:async()=>structuredClone(cmd==='status'?{csrf_token:'fixture'}:
      cmd==='pickerreport'?reports[options.body.get('round')]:response)};};
  const flush=()=>new Promise(resolve=>setImmediate(resolve));
  const press=async element=>{element.listeners.get('click')?.();await flush();};
  const click=async id=>press(nodes.get(id));
  const headings=()=>nodes.get('results').childNodes.map(card=>card.childNodes[0].textContent);
  const buttons=()=>nodes.get('results').childNodes.flatMap(card=>card.childNodes.find(child=>child.className==='result-actions')?.childNodes??[]);
  const roundButtons=()=>nodes.get('result-rounds').childNodes;
  try{
    await import('../webui/web/public/strategy-picker/picker.js?renderer='+Math.random());await flush();
    await check({nodes,calls,requests,click,press,headings,buttons,roundButtons,async update(job,roundReports={}){
      reports=roundReports;response={...response,job};await click('refresh');await flush();}});
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
    assert.match(ui.nodes.get('generation').textContent,/Повторные проверки показали улучшение.*соединением без обхода/);
    assert.match(ui.nodes.get('generation').textContent,/исходная стратегия сохранена. Улучшение по сравнению с ней не подтвердилось/);
    assert.equal(ui.buttons().filter(button=>!button.disabled).length,0);
    await ui.click('language');
    assert.match(ui.nodes.get('generation').textContent,/Repeated checks showed an improvement.*connection without bypass/);
    assert.match(ui.nodes.get('generation').textContent,/kept your original strategy. The new strategy did not show an improvement over it/);
    assert.equal(ui.buttons().filter(button=>!button.disabled).length,0);
    assert.equal(ui.calls.includes('pickerapply'),false);
  });
});

test('Missing or non-boolean pass-through evidence cannot acquire an improvement claim from overall verification',async()=>{
  for(const from_zero of [undefined,null,{}, {eligible:false},{eligible:'true'},{eligible:1}])await withRenderer(async ui=>{
    const job={...case10(),search:'synthesis',skipped:[],generation:{from_zero,versus_current:{eligible:true},verified:true}};
    await ui.update(job);assert.match(ui.nodes.get('generation').textContent,/Проверки пока не показали.*лучше соединения без обхода/);
    await ui.click('language');assert.match(ui.nodes.get('generation').textContent,/have not shown an improvement over the connection without bypass/);
  });
});

test('Improvement over the original requires both its own comparison and overall verification',async()=>{
  for(const [verified,eligible,confirmed] of [[true,true,true],[false,true,false],['true',true,false],[true,'true',false],[true,false,false]])await withRenderer(async ui=>{
    const job={...case10(),search:'synthesis',skipped:[],generation:{from_zero:{eligible:true},versus_current:{eligible},verified}};
    await ui.update(job);
    assert.equal(ui.nodes.get('generation').textContent.includes('Она улучшила результат для выбранных сервисов по сравнению с вашей исходной стратегией.'),confirmed);
    await ui.click('language');
    assert.equal(ui.nodes.get('generation').textContent.includes('It also improved results for the selected services over your original strategy.'),confirmed);
  });
});

test('A stale card cannot apply after its report changes',async()=>{
  const changes=[j=>j.can_apply=false,j=>j.id='d'.repeat(32),j=>j.winner='missing',
    j=>j.state='failed',j=>j.state='cancelled',j=>j.goal='youtube',
    j=>j.profiles[1].runs[1].metrics.tcp.ok=59];
  for(const change of changes)await withRenderer(async ui=>{
    const oldButton=ui.buttons().find(button=>!button.disabled);
    assert.ok(oldButton);
    const job={...case10(),search:'synthesis',skipped:[]};change(job);await ui.update(job);
    await ui.press(oldButton);
    assert.equal(ui.calls.includes('pickerapply'),false);
  });
});

test('Malformed refreshed reports clear cards without offering Apply',async()=>{
  for(const profiles of [null,{},[null],[...case10().profiles,null]])await withRenderer(async ui=>{
    const job={...case10(),search:'synthesis',skipped:[],profiles};await ui.update(job);
    assert.equal(ui.buttons().length,0);
    assert.match(ui.nodes.get('result-feed-status').textContent,/сопоставить|недоступ/);
    assert.equal(ui.nodes.get('results-section').hidden,false);
    assert.equal(ui.nodes.get('generation').textContent,'');
    assert.doesNotMatch(ui.nodes.get('error').textContent,/TypeError|Cannot read/);
  });
});

test('A card applies only its round result in one action with no confirmation',async()=>{
  await withRenderer(async ui=>{
    const j={...case10(),search:'synthesis',skipped:[],series:{current:2,selected:1,total:2,completed:2}};
    const one='a'.repeat(32),two='b'.repeat(32);
    const profile={...j.profiles[1],name:'Вариант обхода · 1'};
    j.measured_results=[one,two].map((id,index)=>({id,round:index+1,number:index+1,name:profile.name,sample_type:'repeated',document_available:true}));
    await ui.update(j,{
      1:{id:j.id,round:1,cards:[{id:one,number:1,profile,can_export:true}]},
      2:{id:j.id,round:2,cards:[{id:two,number:1,profile,can_export:true}]},
    });
    assert.deepEqual(ui.roundButtons().map(button=>button.textContent),['Прогон 1','Прогон 2']);
    assert.deepEqual(ui.headings(),['1-1 Вариант']);
    const detached=ui.buttons()[0];
    await ui.press(ui.roundButtons()[1]);
    assert.deepEqual(ui.headings(),['2-1 Вариант']);
    assert.equal(ui.buttons()[0]['aria-label'],'Применить 2-1');
    await ui.press(detached);
    assert.equal(ui.requests.some(row=>row.cmd==='pickerapply'),false);
    await ui.press(ui.buttons()[0]);
    const sent=ui.requests.filter(row=>row.cmd==='pickerapply');
    assert.equal(sent.length,1);
    assert.equal(sent[0].id,j.id);
    assert.equal(sent[0].result,two);
    assert.equal(ui.nodes.get('confirmation').hidden,true);
    assert.equal(detached['aria-label'],'Применить 1-1');
  });
});
