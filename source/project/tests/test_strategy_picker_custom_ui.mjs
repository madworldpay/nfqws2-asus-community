import assert from 'node:assert/strict';
import {test} from 'node:test';
import {customMeasurements,customComparison,customScope,targetErrors} from '../webui/web/public/strategy-picker/custom.js';
import * as customUI from '../webui/web/public/strategy-picker/custom.js';
import {planSelection} from '../webui/web/public/strategy-picker/concurrency.js';

function mixedPreview(){
  const hosts=['8.8.8.8','alpha.example.com'];
  return {valid:true,hosts,errors:[],schema_version:2,target_policy_version:'custom-public-targets-v2',
    targets:[{kind:'ipv4',host:hosts[0]},{kind:'domain',host:hosts[1]}],sha256:'e'.repeat(64)};
}
function mixedSample(id,flags=[true,false,true,false]){
  const v=sample(id,flags),p=mixedPreview();v.hosts=p.hosts;
  v.cells.forEach((c,i)=>c.host=p.hosts[Math.floor(i/2)]);
  return {...v,schema_version:2,fingerprint:'custom-pinned-root-score-v2',
    probe_fingerprint:'php-openssl-pinned-public-targets-v2',target_policy_version:p.target_policy_version,target_identities:p.targets};
}

test('Mixed measurement rows require typed versioned evidence and preserve each IP TLS minimum',()=>{
  const pair=[mixedSample('1'),mixedSample('2')],v=customMeasurements(pair);
  assert.equal(v?.total,4);assert.equal(v.stable,2);assert.equal(v.rows[0].host,'8.8.8.8');
  for(const change of [p=>p[0].schema_version=1,p=>delete p[0].target_identities,
    p=>p[1].target_identities[0].kind='domain',p=>p[1].fingerprint='custom-pinned-root-score-v1',
    p=>p[1].probe_fingerprint='legacy',p=>p[1].target_policy_version='other',
    p=>p[1].hosts[0]='192.168.1.1']){
    const p=structuredClone(pair);change(p);assert.equal(customMeasurements(p),null);
  }
  const failed=mixedSample('3');failed.cells[0]={host:'8.8.8.8',tls:'tls12',outcome:'tls_error',http_status:null,responded:false,root_ok:false};
  assert.equal(customMeasurements([failed]).rows[0].tls12.low,0);
});

test('Mixed before-after still refuses any IP cell regression and unverified recommendations',()=>{
  const j=report();j.custom_hosts=mixedPreview().hosts;
  j.profiles[0].custom_runs=[mixedSample('1'),mixedSample('2')];
  j.profiles[1].custom_runs=[mixedSample('3',[true,true,true,true]),mixedSample('4',[true,true,true,true])];
  assert.deepEqual(customComparison(j),{before:2,after:4,total:4,repeats:2});
  j.profiles[1].custom_runs[1].cells[0].root_ok=false;j.profiles[1].custom_runs[1].cells[0].http_status=403;
  assert.equal(customComparison(j),null);j.generation.verified=false;assert.equal(customComparison(j),null);
});

test('Mixed scope discloses whole-IP HTTPS effects in RU and EN and rejects special-use targets',()=>{
  for(const language of ['ru','en'])for(const only of [true,false]){
    const s=customScope(mixedPreview().hosts,only,'youtube',language);
    assert.match(s,/8\.8\.8\.8/);assert.match(s,language==='ru'?/другие HTTPS-сайты/:/other HTTPS sites/);
    assert.match(s,/TLS/);
  }
  for(const ip of ['0.0.0.0','10.0.0.1','100.64.0.1','127.0.0.1','169.254.1.1','172.16.0.1','192.0.0.1',
    '192.31.196.1','192.52.193.1','192.88.99.1','192.168.1.1','192.175.48.1','198.18.0.1','198.51.100.1',
    '203.0.113.1','224.0.0.1','255.255.255.255','8.8.8','008.8.8.8','0x8.8.8.8','8.8.8.8/32','[::1]'])
    assert.equal(customScope([ip],true,'all','ru'),null,ip);
});

test('Canonical mixed previews and plans cannot relabel literal identity as a domain',()=>{
  assert.equal(customUI.validTargetPreview?.(mixedPreview()),true);
  for(const change of [p=>delete p.schema_version,p=>p.targets[0].kind='domain',p=>p.sha256='x',
    p=>p.target_policy_version='legacy',p=>p.hosts[0]='192.168.1.1']){
    const p=mixedPreview();change(p);assert.equal(customUI.validTargetPreview?.(p),false);
  }
  const s=planSelection({search:'synthesis',extended:false,goal:'all',custom:{hosts:mixedPreview().hosts,only:true},requested:'32'});
  assert.equal(s.custom_target_policy,'custom-public-targets-v2');assert.deepEqual(s.custom_targets,mixedPreview().targets);
});

test('Mixed line errors explain non-public addresses and CIDR without copying private input',()=>{
  for(const language of ['ru','en']){
    const text=targetErrors([{line:2,code:'non_public_ipv4',raw:'SECRET'},{line:3,code:'cidr_not_allowed'}],language);
    assert.match(text,/IPv4/);assert.match(text,/CIDR/);assert.match(text,/2/);assert.match(text,/3/);assert.doesNotMatch(text,/SECRET/);
  }
});

function sample(id,flags=[true,false,true,false]){
  const hosts=['alpha.example.com','beta.example.com'];
  return {schema_version:1,fingerprint:'custom-pinned-root-score-v1',probe_fingerprint:'pinned-root-fixture',
    hosts,dns_context:'c'.repeat(64),context_sha256:'d'.repeat(64),manifest_sha256:'e'.repeat(64),
    sample_id:id.repeat(32),sample_sha256:'f'.repeat(64),targets:'a'.repeat(64),
    cells:flags.map((ok,i)=>({host:hosts[Math.floor(i/2)],tls:i%2?'tls13':'tls12',outcome:'response',
      http_status:ok?200:403,responded:true,root_ok:ok}))};
}
function report(){
  const native=()=>({targets:'b'.repeat(64),context_sha256:'d'.repeat(64),
    metrics:Object.fromEntries(['tcp','http','tls12','tls13','quic'].map(k=>[k,{ok:1,total:1}]))});
  return {id:'1'.repeat(32),state:'completed',restored:true,goal:'all',custom_hosts:['alpha.example.com','beta.example.com'],
    custom_only:true,can_apply:true,can_export:true,generation:{verified:true},winner:'new:s-final',generated:'new:s-final',profiles:[
      {id:'old',name:'Original',rank:{reason:'baseline'},sample_type:'repeated',runs:[native(),native()],custom_runs:[sample('1'),sample('2')]},
      {id:'new',recipe:'s-final',name:'Final',rank:{eligible:true},sample_type:'repeated',runs:[native(),native()],custom_runs:[sample('3',[true,true,true,true]),sample('4',[true,true,true,true])]}]};
}

test('Custom root success stays separate from transport responses and uses cellwise repeated minima',()=>{
  const pair=[sample('1',[true,false,true,false]),sample('2',[false,true,false,true])];
  const v=customMeasurements(pair);
  assert.equal(v.repeats,2);assert.equal(v.total,4);assert.equal(v.stable,0);assert.equal(v.responded,4);
  assert.deepEqual(v.rows[0],{host:'alpha.example.com',tls12:{low:0,high:1},tls13:{low:0,high:1}});
  assert.equal(customMeasurements([sample('1')]).repeats,1);
});

test('Malformed, replayed or incomparable custom samples never become visible success ratios',()=>{
  for(const change of [p=>p[1].sample_id=p[0].sample_id,p=>p[1].targets='b'.repeat(64),
    p=>p[1].context_sha256='b'.repeat(64),p=>p[1].cells.pop(),p=>p[1].cells[0].root_ok='true',
    p=>p[1].cells[0].root_ok=false,p=>p[1].cells[0].host='other.example.com',p=>p[1].hosts=['alpha.example.com'],
    p=>p[1].cells[0].responded=false]){
    const pair=[sample('1'),sample('2')];change(pair);assert.equal(customMeasurements(pair),null);
  }
  for(const value of [null,{},[],[null]])assert.equal(customMeasurements(value),null);
});

test('Before and after compare only the original with the verified final repeated sample',()=>{
  const job=report(),v=customComparison(job);
  assert.deepEqual(v,{before:2,after:4,total:4,repeats:2});
  const zero=structuredClone(job.profiles[0]);zero.rank={reason:'zero_baseline'};zero.custom_runs=[sample('5',[false,false,false,false]),sample('6',[false,false,false,false])];
  job.profiles.splice(1,0,zero);assert.deepEqual(customComparison(job),v);
  for(const change of [j=>j.can_export=false,j=>j.generation.verified=false,j=>j.state='failed',
    j=>j.profiles[2].sample_type='exploratory',j=>j.profiles.push(j.profiles[0]),
    j=>j.profiles[2].custom_runs[1].targets='b'.repeat(64),j=>j.custom_hosts=['other.com']]){
    const j=structuredClone(job);change(j);assert.equal(customComparison(j),null);
  }
});

test('A custom cell regression cannot hide behind a bigger total in the before-after summary',()=>{
  const j=report();j.profiles[1].custom_runs=[sample('3',[false,true,true,true]),sample('4',[false,true,true,true])];
  assert.equal(customComparison(j),null);
});

test('The measured custom-only and joint scope names every site in both languages',()=>{
  const j=report();
  for(const language of ['ru','en']){
    const only=customScope(j.custom_hosts,true,'all',language),joint=customScope(j.custom_hosts,false,'youtube,discord',language);
    assert.ok(only.includes('alpha.example.com')&&only.includes('beta.example.com'));
    assert.match(joint,/YouTube.*Discord/);
    assert.match(only,/свои сайты|custom sites/i);
  }
  for(const hosts of [[],null,['<img src=x>'],['t.me'],['a.com','a.com']])assert.equal(customScope(hosts,true,'all','ru'),null);
});

test('Per-line validation errors do not quote raw URLs, markup or secrets',()=>{
  for(const language of ['ru','en']){
    const message=targetErrors([{line:2,code:'port_not_allowed'},{line:3,code:'telegram_excluded',raw:'SECRET'},
      {line:0,code:'input_too_long'}],language);
    assert.match(message,/2/);assert.match(message,/3/);assert.match(message,/4096/);
    assert.doesNotMatch(message,/SECRET|<|>/);
  }
});

async function withUi(check,{preview,plan,mutation,status,job=null,capability=true,savedMutation=null}={}){
  const previous={document:globalThis.document,window:globalThis.window,fetch:globalThis.fetch,setTimeout:globalThis.setTimeout,clearTimeout:globalThis.clearTimeout,sessionStorage:globalThis.sessionStorage};
  const nodes=new Map(),events=new Map(),requests=[],navigation=[],downloads=[],deadlines=new Map(),stored=new Map();
  if(savedMutation)stored.set('nfqws-picker-pending-v1',JSON.stringify(savedMutation));
  globalThis.sessionStorage={getItem:k=>stored.get(k)??null,setItem:(k,v)=>stored.set(k,v),removeItem:k=>stored.delete(k)};
  globalThis.setTimeout=(fn,ms,...args)=>{if(ms===15000){const id={};deadlines.set(id,fn);return id;}return previous.setTimeout(fn,ms,...args);};
  globalThis.clearTimeout=id=>{if(!deadlines.delete(id))previous.clearTimeout(id);};
  const element=tagName=>({tagName,hidden:false,disabled:false,checked:false,value:'',textContent:'',childNodes:[],
    listeners:new Map(),classList:{toggle(){}},append(v){this.childNodes.push(v);},replaceChildren(...children){this.childNodes=children;},
    click(){if(this.download)downloads.push(this.download);},
    addEventListener(type,listener){this.listeners.set(type,listener);}});
  const document={hidden:false,documentElement:{lang:'ru'},addEventListener(){},removeEventListener(){},
    createElement:element,getElementById(id){if(!nodes.has(id))nodes.set(id,element());return nodes.get(id);}};
  document.getElementById('search').value='synthesis';document.getElementById('goal-all').checked=true;
  document.getElementById('goal-youtube').checked=true;document.getElementById('custom-joint').checked=true;
  document.getElementById('confirmation').hidden=true;
  const budget={cores:4,available_kib:3000000,load:0,concurrency:10,deadline_seconds:2700,max_profiles:5};
  let response={active:job?.state==='running',job,detector:{installed:true},error:null,budget,generator:{max_trials:14},
    custom_capability:capability?{available:true,budget:{...budget,deadline_seconds:6480},scope:'all_controls'}:
      {available:false,code:'insufficient_memory'}};
  globalThis.document=document;globalThis.window={addEventListener(type,fn){events.set(type,fn);},location:{assign(url){navigation.push(url);}}};
  globalThis.fetch=async(url,options)=>{
    assert.equal(url,'/index.php');const p=Object.fromEntries(options.body);requests.push(p);
    const value=p.cmd==='status'?{csrf_token:'fixture'}:p.cmd==='pickertargets'?
      await (preview?.(p)??{valid:true,hosts:['alpha.example.com','beta.example.com'],errors:[]}):p.cmd==='pickerplan'?
      await (plan?.(p)??fixturePlan(p,budget)):p.cmd==='pickerstatus'?
      await (status?.(p,options,response)??response):await (mutation?.(p,options,response)??response);
    return {ok:!value?.fixture_status,status:value?.fixture_status||200,json:async()=>structuredClone(value)};
  };
  const flush=()=>new Promise(r=>setImmediate(r));
  const fire=(id,type='click')=>document.getElementById(id).listeners.get(type)?.();
  const click=async id=>{await fire(id);await flush();};
  const set=(id,values)=>Object.assign(document.getElementById(id),values);
  try{
    await import('../webui/web/public/strategy-picker/picker.js?custom-test='+Math.random());await flush();
    await check({nodes,requests,navigation,downloads,fire,click,flush,set,stored,async timeout(){assert.ok(deadlines.size,'request must have a finite timeout');[...deadlines.values()].forEach(fn=>fn());await flush();await flush();},async update(next){response={...response,...next};await click('refresh');}});
  }finally{
    events.get('pagehide')?.();for(const [key,value]of Object.entries(previous)){
      if(value===undefined)delete globalThis[key];else globalThis[key]=value;
    }
  }
}

test('A failed series retains selectable results and hands off only the sealed choice to Import',async()=>{
  const id='a'.repeat(32),early='2'.repeat(32),late='3'.repeat(32);
  const first={id:early,number:1,round:1,name:'First result',sample_type:'repeated',document_available:true};
  const second={id:late,number:2,round:2,name:'Completed measurements',sample_type:'repeated',document_available:false};
  const job={...report(),id,state:'failed',code:'service_stop_failed',can_apply:false,can_export:false,
    profiles:[],restored:true,measured_results:[first,second]};
  await withUi(async({nodes,requests,navigation,downloads,fire,click,flush,set,stored})=>{
    assert.equal(nodes.get('measured-section').hidden,false);
    assert.equal(nodes.get('apply').hidden,true);
    assert.deepEqual(nodes.get('measured-select').childNodes.map(n=>n.value),['',early,late]);
    set('measured-select',{value:late});await fire('measured-select','change');await flush();
    assert.equal(nodes.get('measured-report').hidden,false);
    assert.equal(nodes.get('measured-export').hidden,true);
    assert.equal(nodes.get('measured-import').hidden,true);
    set('measured-select',{value:early});await fire('measured-select','change');await flush();
    assert.equal(nodes.get('measured-import').hidden,false);
    await click('measured-export');
    assert.deepEqual(downloads,['NFQWS2_MEASURED_'+early+'.json']);
    await click('measured-import');
    assert.deepEqual(navigation,['/?picker-import=1']);
    assert.deepEqual(JSON.parse(stored.get('nfqws-picker-import-v1')),{id,result:early});
    assert.deepEqual(requests.filter(r=>['pickerexport','pickerapply'].includes(r.cmd)),[
      {cmd:'pickerexport',csrf_token:'fixture',id,result:early},
    ]);
  },{job,mutation:p=>{
    if(p.cmd==='pickerresult'){
      const selected=p.result===early?first:second;
      return {id:selected.id,round:selected.round,can_export:selected.document_available,
        profile:{name:selected.name,sample_type:selected.sample_type,runs:report().profiles[0].runs}};
    }
    if(p.cmd==='pickerexport')return {filename:'NFQWS2_MEASURED_'+p.result+'.json',raw:'{"fixture":true}'};
  }});
});

function fixturePlan(p,budget={cores:4,available_kib:3000000,load:0,concurrency:10,deadline_seconds:2700,max_profiles:5}){
  const selection={search:p.search,extended:p.extended==='1',goal:p.goal},requested=p.concurrency||'auto',effective=requested==='auto'?10:Number(requested);
  if(requested!=='auto')selection.concurrency=requested;
  if(Number(p.rounds)>1)selection.rounds=Number(p.rounds);
  if(p.custom_sites){selection.custom_hosts=p.custom_sites.split('\n').sort();selection.custom_only=p.custom_only==='1';}
  if(selection.custom_hosts?.some(h=>/^\d+\.\d+\.\d+\.\d+$/.test(h))){
    selection.custom_target_policy='custom-public-targets-v2';
    selection.custom_targets=selection.custom_hosts.map(host=>({kind:/^\d+\.\d+\.\d+\.\d+$/.test(host)?'ipv4':'domain',host}));
  }
  return {available:true,version:'picker-start-plan-v1',selection,budget:{...budget,concurrency:effective,
    deadline_seconds:p.custom_sites?(effective===2?14220:6480):2700},
    concurrency_choice:{policy_version:'picker-concurrency-v1',requested,effective,admission:null},plan_sha256:'a'.repeat(64)};
}

test('Mixed IP UI uses the same single goal/pool/scope confirmation and canonical mutation',async()=>{
  for(const language of ['ru','en'])await withUi(async ui=>{
    if(language==='en')await ui.click('language');
    ui.set('custom-enabled',{checked:true});ui.set('custom-sites',{value:'HTTPS://8.8.8.8/path\nALPHA.EXAMPLE.COM'});
    ui.set('pool-auto',{checked:false});ui.set('pool-manual',{checked:true});ui.set('pool-value',{value:'32'});ui.fire('pool-value','input');
    await ui.click('start');assert.equal(ui.nodes.get('confirmation').hidden,false);
    const text=ui.nodes.get('confirmation-text').textContent;
    assert.match(text,/8\.8\.8\.8/);assert.match(text,/32/);assert.match(text,language==='ru'?/другие HTTPS-сайты/:/other HTTPS sites/);
    assert.equal(ui.requests.some(p=>p.cmd==='pickersynthesize'),false);await ui.click('confirm-submit');
    const sent=ui.requests.find(p=>p.cmd==='pickersynthesize');
    assert.equal(sent.custom_sites,'8.8.8.8\nalpha.example.com');assert.equal(sent.custom_only,'0');assert.equal(sent.concurrency,'32');
    assert.equal(sent.plan_sha256,'a'.repeat(64));
  },{preview:mixedPreview});
});

test('An incomplete or relabelled IP preview never acquires consent or a plan',async()=>{
  for(const change of [p=>delete p.schema_version,p=>p.targets[0].kind='domain'])await withUi(async ui=>{
    ui.set('custom-enabled',{checked:true});ui.set('custom-sites',{value:'8.8.8.8\nalpha.example.com'});
    await ui.click('start');assert.equal(ui.nodes.get('confirmation').hidden,true);
    assert.equal(ui.requests.some(p=>['pickerplan','pickersynthesize'].includes(p.cmd)),false);
  },{preview:()=>{const p=mixedPreview();change(p);return p;}});
});

test('Reloaded mixed timeout request retains its canonical IP scope pool plan and id',async()=>{
  const savedMutation={cmd:'pickersynthesize',extra:{request_id:'a'.repeat(32),consent:'test',goal:'all',
    custom_sites:'8.8.8.8\nalpha.example.com',custom_only:'1',concurrency:'32',plan_sha256:'b'.repeat(64)}};
  await withUi(async ui=>{
    await ui.click('start');assert.equal(ui.nodes.get('confirmation').hidden,false);
    assert.match(ui.nodes.get('confirmation-text').textContent,/8\.8\.8\.8/);
    await ui.click('confirm-submit');
    const sent=ui.requests.find(p=>p.cmd==='pickersynthesize');
    assert.deepEqual(Object.fromEntries(Object.entries(sent).filter(([k])=>!['cmd','csrf_token'].includes(k))),savedMutation.extra);
  },{savedMutation});
});

test('Mixed recovery retains the recorded selection and disables every editing group',async()=>{
  await withUi(async ui=>{
    for(const id of ['custom-fieldset','pool-fieldset','goals','search','extended'])assert.equal(ui.nodes.get(id).disabled,true,id);
    assert.equal(ui.nodes.get('custom-sites').value,'8.8.8.8\nalpha.example.com');
    assert.equal(ui.nodes.get('custom-only').checked,true);
    assert.equal(ui.nodes.get('start').disabled,true);
  },{job:{...report(),state:'recovery_required',phase:'recovery_required',search:'synthesis',
    custom_hosts:mixedPreview().hosts,concurrency_choice:{policy_version:'picker-concurrency-v1',requested:'32',effective:32},
    budget:{cores:4,available_kib:3000000,load:0,concurrency:32,deadline_seconds:6480,max_profiles:5}}});
});

test('Manual request pool is planned before the existing single confirmation and sent exactly',async()=>{
  await withUi(async ui=>{
    ui.set('pool-auto',{checked:false});ui.set('pool-manual',{checked:true});ui.set('pool-value',{value:'32'});ui.fire('pool-value','input');
    assert.match(ui.nodes.get('limits').textContent,/32/);assert.doesNotMatch(ui.nodes.get('limits').textContent,/Параллельность: 10/);
    await ui.click('start');assert.equal(ui.requests.filter(p=>p.cmd==='pickerplan').length,1);
    assert.equal(ui.requests.some(p=>p.cmd==='pickersynthesize'),false);assert.equal(ui.nodes.get('confirmation').hidden,false);
    assert.match(ui.nodes.get('confirmation-text').textContent,/32/);await ui.click('confirm-submit');
    const sent=ui.requests.filter(p=>p.cmd==='pickersynthesize');assert.equal(sent.length,1);
    assert.equal(sent[0].concurrency,'32');assert.equal(sent[0].plan_sha256,'a'.repeat(64));
  });
});

test('Invalid manual syntax never reaches planning or mutation',async()=>{
  for(const value of ['0','01','+1','1e2','1000001','1.0',' 32',''])await withUi(async ui=>{
    ui.set('pool-auto',{checked:false});ui.set('pool-manual',{checked:true});ui.set('pool-value',{value});ui.fire('pool-value','input');
    assert.equal(ui.nodes.get('start').disabled,true);await ui.click('start');
    assert.equal(ui.requests.some(p=>p.cmd==='pickerplan'||p.cmd==='pickersynthesize'),false);
  });
});

test('Pool changes invalidate consent and a delayed plan cannot approve the newer pool',async()=>{
  await withUi(async ui=>{
    await ui.click('start');assert.equal(ui.nodes.get('confirmation').hidden,false);
    ui.set('pool-auto',{checked:false});ui.set('pool-manual',{checked:true});ui.set('pool-value',{value:'32'});ui.fire('pool-value','input');
    await ui.click('confirm-submit');assert.equal(ui.requests.some(p=>p.cmd==='pickersynthesize'),false);
  });
  let finish;
  await withUi(async ui=>{
    const pending=ui.fire('start');await ui.flush();ui.set('pool-auto',{checked:false});ui.set('pool-manual',{checked:true});ui.set('pool-value',{value:'32'});ui.fire('pool-value','input');
    finish();await pending;await ui.flush();assert.equal(ui.nodes.get('confirmation').hidden,true);
  },{plan:p=>new Promise(r=>{finish=()=>r(fixturePlan(p));})});
});

test('Unsupported resources and changed plan bindings close confirmation without a start',async()=>{
  await withUi(async ui=>{await ui.click('start');assert.equal(ui.nodes.get('confirmation').hidden,true);
    assert.equal(ui.requests.some(p=>p.cmd==='pickersynthesize'),false);assert.match(ui.nodes.get('error').textContent,/памяти/);
  },{plan:()=>({error:'insufficient_memory'})});
  let count=0;
  await withUi(async ui=>{await ui.click('start');assert.equal(ui.nodes.get('confirmation').hidden,false);
    await ui.click('refresh');assert.equal(ui.nodes.get('confirmation').hidden,true);await ui.click('confirm-submit');
    assert.equal(ui.requests.some(p=>p.cmd==='pickersynthesize'),false);
  },{plan:p=>({...fixturePlan(p),plan_sha256:(++count===1?'a':'b').repeat(64)})});
});

test('Reload shows actual recorded manual pool and disables it throughout recovery',async()=>{
  for(const state of ['running','recovery_required'])await withUi(async ui=>{
    assert.equal(ui.nodes.get('pool-fieldset').disabled,true);
    assert.equal(ui.nodes.get('pool-value').value,'32');assert.match(ui.nodes.get('pool-selected').textContent,/32/);
    await ui.click('language');assert.match(ui.nodes.get('pool-selected').textContent,/one strategy/i);
  },{job:{...report(),state,phase:state,search:'synthesis',skipped:[],concurrency_valid:true,
    concurrency_choice:{policy_version:'picker-concurrency-v1',requested:'32',effective:32},
    budget:{cores:4,available_kib:3000000,load:0,concurrency:32,deadline_seconds:6480,max_profiles:5}}});
});

test('Numeric pool keeps 10 through 1000000 with reported low memory',async()=>{
  await withUi(async ui=>{
    for(const n of [10,100,10000,30000,250000,1000000]){
      ui.set('pool-value',{value:String(n)});ui.fire('pool-value','input');
      assert.equal(ui.nodes.get('pool-value').value,String(n));
      await ui.click('start');
      assert.equal(ui.requests.filter(p=>p.cmd==='pickerplan').at(-1).concurrency,String(n));
      assert.match(ui.nodes.get('confirmation-text').textContent,new RegExp(String(n)));
      if(n===1000000)await ui.click('confirm-submit');else await ui.click('confirm-dismiss');
    }
    assert.equal(ui.requests.find(p=>p.cmd==='pickersynthesize').concurrency,'1000000');
  },{plan:p=>fixturePlan(p,{cores:2,available_kib:23000,load:0,concurrency:10,deadline_seconds:2700,max_profiles:5})});
});

test('Completion counter distinguishes an estimate from a deadline',async()=>{
  const picker=await import('../webui/web/public/strategy-picker/picker.js?timing506');
  const job={state:'running',progress:25,elapsed_seconds:120,remaining_seconds:2580};
  const ru=picker.remainingTime?.(job,true,0,'ru');
  assert.match(ru??'',/6 мин/);assert.doesNotMatch(ru,/43 мин|предел|лимит/);
  assert.match(picker.remainingTime?.(job,true,60,'en')??'',/5 min/);
  assert.match(picker.remainingTime?.({...job,progress:0},true,0,'ru')??'',/первых проверок/);
  assert.equal(picker.remainingTime?.(job,false,0,'ru'),'');
  assert.equal(picker.remainingTime?.({...job,elapsed_seconds:undefined},true,0,'ru'),'');
});

test('Manual timeout retries and a reloaded saved request retain exactly their pool and plan',async()=>{
  let attempts=0,offline=false;
  await withUi(async ui=>{
    ui.set('pool-auto',{checked:false});ui.set('pool-manual',{checked:true});ui.set('pool-value',{value:'32'});ui.fire('pool-value','input');
    await ui.click('start');await ui.click('confirm-submit');assert.ok(ui.stored.size);
    offline=false;await ui.click('start');await ui.click('confirm-submit');
    const sent=ui.requests.filter(p=>p.cmd==='pickersynthesize');assert.equal(sent.length,2);assert.deepEqual(sent[0],sent[1]);
    assert.equal(sent[1].concurrency,'32');assert.equal(sent[1].plan_sha256,'a'.repeat(64));
  },{mutation:(p,options,response)=>{if(++attempts===1){offline=true;throw new TypeError('offline');}return {...response,active:true,job:runningJob(p.request_id)};},
    status:(p,options,response)=>{if(offline)throw new TypeError('offline');return response;}});
  const savedMutation={cmd:'pickersynthesize',extra:{request_id:'a'.repeat(32),consent:'test',goal:'all',concurrency:'32',plan_sha256:'b'.repeat(64)}};
  await withUi(async ui=>{
    assert.equal(ui.nodes.get('pool-value').value,'32');assert.equal(ui.nodes.get('pool-fieldset').disabled,true);
    await ui.click('start');assert.match(ui.nodes.get('confirmation-text').textContent,/32/);await ui.click('confirm-submit');
    const sent=ui.requests.find(p=>p.cmd==='pickersynthesize');assert.equal(sent.concurrency,'32');assert.equal(sent.plan_sha256,'b'.repeat(64));
  },{savedMutation});
});

test('A newly active report cancels pending planning and leaves the actual Cancel button usable',async()=>{
  let plans=0;
  await withUi(async ui=>{
    await ui.click('start');assert.equal(ui.nodes.get('confirmation').hidden,false);
    await ui.update({active:true,job:runningJob('f'.repeat(32))});
    assert.equal(ui.nodes.get('confirmation').hidden,true);assert.equal(ui.nodes.get('cancel').hidden,false);
    assert.equal(ui.nodes.get('pool-fieldset').disabled,true);
  },{plan:p=>++plans===1?fixturePlan(p):{error:'busy'}});
});

test('Malformed plan pool, scope or hash cannot acquire consent',async()=>{
  for(const change of [p=>p.concurrency_choice.effective='10',p=>p.selection.goal='youtube',
    p=>p.plan_sha256='bad',p=>p.budget.concurrency=32,p=>p.available='true'])await withUi(async ui=>{
    await ui.click('start');assert.equal(ui.nodes.get('confirmation').hidden,true);
    assert.equal(ui.requests.some(p=>p.cmd==='pickersynthesize'),false);
  },{plan:p=>{const v=fixturePlan(p);change(v);return v;}});
});

test('Joint start previews before consent and sends only canonical hosts after confirmation',async()=>{
  await withUi(async ui=>{
    ui.set('custom-enabled',{checked:true});ui.set('custom-sites',{value:'https://ALPHA.example.com/private?token=SECRET\nbeta.example.com'});ui.fire('custom-enabled','change');
    assert.match(ui.nodes.get('limits').textContent,/100/);assert.doesNotMatch(ui.nodes.get('limits').textContent,/45/);
    await ui.click('start');
    assert.equal(ui.requests.filter(p=>p.cmd==='pickertargets').length,1);
    assert.equal(ui.requests.some(p=>p.cmd==='pickersynthesize'),false);
    assert.equal(ui.nodes.get('confirmation').hidden,false);
    assert.match(ui.nodes.get('confirmation-text').textContent,/alpha\.example\.com.*beta\.example\.com/);
    assert.doesNotMatch(ui.nodes.get('confirmation-text').textContent,/SECRET|private/);
    await ui.click('confirm-submit');
    const sent=ui.requests.filter(p=>p.cmd==='pickersynthesize');assert.equal(sent.length,1);
    assert.equal(sent[0].custom_sites,'alpha.example.com\nbeta.example.com');assert.equal(sent[0].custom_only,'0');
    assert.equal(sent[0].goal,'all');assert.match(sent[0].request_id,/^[a-f0-9]{32}$/);
  });
});

test('Custom-only mode works with no native service selected while joint mode requires a goal',async()=>{
  await withUi(async ui=>{
    ui.set('custom-enabled',{checked:true});ui.set('custom-sites',{value:'alpha.example.com\nbeta.example.com'});
    ui.set('goal-all',{checked:false});ui.set('goal-selected',{checked:true});for(const service of ['youtube','discord','instagram','torrents'])ui.set('goal-'+service,{checked:false});
    ui.fire('custom-enabled','change');await ui.click('start');
    assert.equal(ui.requests.some(p=>p.cmd==='pickertargets'),false);
    ui.set('custom-only',{checked:true});ui.set('custom-joint',{checked:false});ui.fire('custom-only','change');
    await ui.click('start');await ui.click('confirm-submit');
    const p=ui.requests.find(p=>p.cmd==='pickersynthesize');assert.ok(p);assert.equal(p.custom_only,'1');assert.equal(p.goal,'all');
  });
});

test('Invalid or incomplete custom preview never opens confirmation or starts a job',async()=>{
  for(const preview of [{valid:false,hosts:[],errors:[{line:2,code:'port_not_allowed'}]},
    {valid:true,hosts:[],errors:[]}])await withUi(async ui=>{
    ui.set('custom-enabled',{checked:true});ui.set('custom-sites',{value:'alpha.example.com\nbeta.example.com:443'});ui.fire('custom-enabled','change');
    await ui.click('start');assert.equal(ui.nodes.get('confirmation').hidden,true);
    assert.equal(ui.requests.some(p=>p.cmd==='pickersynthesize'),false);
    assert.ok(ui.nodes.get('custom-errors').textContent||ui.nodes.get('error').textContent);
  },{preview:()=>preview});
});

test('Changing a custom draft or search mode invalidates its pending confirmation',async()=>{
  for(const change of [ui=>{ui.set('custom-sites',{value:'changed.example.com'});ui.fire('custom-sites','input');},
    ui=>{ui.set('search',{value:'profiles'});ui.fire('search','change');},ui=>ui.fire('language')])await withUi(async ui=>{
    ui.set('custom-enabled',{checked:true});ui.set('custom-sites',{value:'alpha.example.com\nbeta.example.com'});ui.fire('custom-enabled','change');
    await ui.click('start');assert.equal(ui.nodes.get('confirmation').hidden,false);change(ui);
    await ui.click('confirm-submit');assert.equal(ui.nodes.get('confirmation').hidden,true);
    assert.equal(ui.requests.some(p=>p.cmd==='pickersynthesize'||p.cmd==='pickerstart'),false);
  });
});

test('A delayed preview cannot approve a newer draft',async()=>{
  let finish;
  await withUi(async ui=>{
    ui.set('custom-enabled',{checked:true});ui.set('custom-sites',{value:'alpha.example.com'});ui.fire('custom-enabled','change');
    const pending=ui.fire('start');await ui.flush();ui.set('custom-sites',{value:'changed.example.com'});ui.fire('custom-sites','input');
    finish({valid:true,hosts:['alpha.example.com'],errors:[]});await pending;await ui.flush();
    assert.equal(ui.nodes.get('confirmation').hidden,true);assert.equal(ui.requests.some(p=>p.cmd==='pickersynthesize'),false);
  },{preview:()=>new Promise(r=>{finish=r;})});
});

test('Session expiry during preview or confirmation clears actions until reload',async()=>{
  await withUi(async ui=>{
    ui.set('custom-enabled',{checked:true});ui.set('custom-sites',{value:'alpha.example.com'});ui.fire('custom-enabled','change');
    await ui.click('start');assert.equal(ui.nodes.get('confirmation').hidden,true);assert.equal(ui.nodes.get('start').disabled,true);
    await ui.click('confirm-submit');assert.equal(ui.requests.some(p=>p.cmd==='pickersynthesize'),false);
  },{preview:()=>({fixture_status:403})});
  await withUi(async ui=>{
    ui.set('custom-enabled',{checked:true});ui.set('custom-sites',{value:'alpha.example.com'});ui.fire('custom-enabled','change');
    await ui.click('start');assert.equal(ui.nodes.get('confirmation').hidden,false);
    await ui.update({fixture_status:401});assert.equal(ui.nodes.get('confirmation').hidden,true);
    await ui.click('confirm-submit');assert.equal(ui.requests.some(p=>p.cmd==='pickersynthesize'),false);
  });
});

test('Dismissing a preview leaves no job and stopping an active job sends only its bound id',async()=>{
  await withUi(async ui=>{
    ui.set('custom-enabled',{checked:true});ui.set('custom-sites',{value:'alpha.example.com'});ui.fire('custom-enabled','change');
    await ui.click('start');await ui.click('confirm-dismiss');await ui.click('confirm-submit');
    assert.equal(ui.requests.some(p=>p.cmd==='pickersynthesize'),false);
    await ui.update({active:true,job:{...report(),search:'synthesis',state:'running',phase:'measuring_1',skipped:[],
      budget:{cores:4,available_kib:3000000,load:0,concurrency:10,deadline_seconds:6480,max_profiles:5}}});
    await ui.click('cancel');const sent=ui.requests.filter(p=>p.cmd==='pickercancel');assert.equal(sent.length,1);
    assert.deepEqual(Object.keys(sent[0]).sort(),['cmd','csrf_token','id']);assert.equal(sent[0].id,'1'.repeat(32));
  });
});

test('Unavailable custom memory admission blocks starting and a profile comparison sends no hidden custom fields',async()=>{
  await withUi(async ui=>{
    ui.set('custom-enabled',{checked:true});ui.fire('custom-enabled','change');
    assert.equal(ui.nodes.get('start').disabled,true);await ui.click('start');
    assert.equal(ui.requests.some(p=>p.cmd==='pickertargets'||p.cmd==='pickersynthesize'),false);
    ui.set('search',{value:'profiles'});ui.fire('search','change');await ui.click('start');await ui.click('confirm-submit');
    const sent=ui.requests.find(p=>p.cmd==='pickerstart');assert.ok(sent);assert.equal(sent.custom_sites,undefined);
  },{capability:false});
});

test('Reload restores the actual active custom scope and keeps every editing control disabled',async()=>{
  const job={...report(),search:'synthesis',state:'running',phase:'measuring_1',budget:{cores:4,available_kib:3000000,
    load:0,concurrency:10,deadline_seconds:6480,max_profiles:5},skipped:[]};
  await withUi(async ui=>{
    assert.equal(ui.nodes.get('custom-enabled').checked,true);assert.equal(ui.nodes.get('custom-only').checked,true);
    assert.equal(ui.nodes.get('custom-sites').value,'alpha.example.com\nbeta.example.com');
    assert.equal(ui.nodes.get('custom-fieldset').disabled,true);assert.equal(ui.nodes.get('goals').disabled,true);
    assert.equal(ui.nodes.get('start').disabled,true);assert.equal(ui.nodes.get('cancel').hidden,false);
    assert.match(ui.nodes.get('limits').textContent,/14/);
    await ui.click('language');assert.match(ui.nodes.get('custom-help').textContent,/TLS 1\.2.*1\.3/);
  },{job});
});

test('A custom-only recommendation names its measured scope and its Apply confirmation names the sites',async()=>{
  await withUi(async ui=>{
    assert.match(ui.nodes.get('winner').textContent,/свои сайты/i);assert.doesNotMatch(ui.nodes.get('winner').textContent,/все сервисы/i);
    await ui.click('apply');assert.match(ui.nodes.get('confirmation-text').textContent,/alpha\.example\.com.*beta\.example\.com/);
    assert.equal(ui.requests.some(p=>p.cmd==='pickerapply'),false);
  },{job:{...report(),search:'synthesis',skipped:[]}});
});

function runningJob(request){return {...report(),request_id:request,search:'synthesis',state:'running',phase:'measuring_1',skipped:[],
 budget:{cores:4,available_kib:3000000,load:0,concurrency:10,deadline_seconds:6480,max_profiles:5}};}
function neverUntilAbort(options){return new Promise((resolve,reject)=>{
  options.signal?.addEventListener('abort',()=>reject(new DOMException('aborted','AbortError')),{once:true});});}

test('A lost accepted start response times out, reconciles its request and leaves Cancel usable',async()=>{
  let accepted=null;
  await withUi(async ui=>{
    await ui.click('start');await ui.click('confirm-submit');await ui.timeout();
    assert.equal(ui.nodes.get('cancel').hidden,false);assert.equal(ui.nodes.get('cancel').disabled,false);
    assert.equal(ui.requests.filter(p=>p.cmd==='pickersynthesize').length,1);
    assert.doesNotMatch(ui.nodes.get('error').textContent,/Достигнут предел времени|остановлен/);
    assert.equal(ui.stored.size,0);
  },{mutation:(p,options)=>{accepted=p.request_id;return neverUntilAbort(options);},
    status:(p,options,response)=>accepted?{...response,active:true,job:runningJob(accepted)}:response});
});

test('An ambiguous start retry retains exactly the canonical payload and request id',async()=>{
  let attempts=0,offline=false;
  await withUi(async ui=>{
    ui.set('custom-enabled',{checked:true});ui.set('custom-sites',{value:'https://ALPHA.example.com/private?token=SECRET\nbeta.example.com'});ui.fire('custom-enabled','change');
    await ui.click('start');await ui.click('confirm-submit');await ui.flush();
    assert.equal(ui.nodes.get('start').disabled,false);assert.equal(ui.nodes.get('custom-fieldset').disabled,true);
    assert.ok(ui.stored.size);assert.doesNotMatch([...ui.stored.values()].join(''),/SECRET|private/);
    offline=false;await ui.click('start');await ui.click('confirm-submit');await ui.flush();
    const sent=ui.requests.filter(p=>p.cmd==='pickersynthesize');assert.equal(sent.length,2);assert.deepEqual(sent[1],sent[0]);
    assert.equal(ui.stored.size,0);
  },{mutation:(p,options,response)=>{if(++attempts===1){offline=true;throw new TypeError('network lost');}return {...response,active:true,job:runningJob(p.request_id)};},
    status:(p,options,response)=>{if(offline)throw new TypeError('network lost');return response;}});
});

test('A stalled Cancel times out without claiming cancellation and can retry only its bound job',async()=>{
  let attempts=0;const job=runningJob('2'.repeat(32));
  await withUi(async ui=>{
    await ui.click('cancel');await ui.timeout();
    assert.equal(ui.nodes.get('cancel').hidden,false);assert.equal(ui.nodes.get('cancel').disabled,false);
    assert.match(ui.nodes.get('error').textContent,/ответ|продолж/);
    await ui.click('cancel');await ui.flush();
    const sent=ui.requests.filter(p=>p.cmd==='pickercancel');assert.equal(sent.length,2);assert.deepEqual(sent[1],sent[0]);
    assert.equal(ui.nodes.get('cancel').hidden,true);assert.equal(ui.stored.size,0);
  },{job,mutation:(p,options,response)=>++attempts===1?neverUntilAbort(options):
    {...response,active:false,job:{...job,state:'cancelled',restored:true}}});
});


test('Completion counter estimates an unlimited search without presenting a stop deadline',async()=>{
  const picker=await import('../webui/web/public/strategy-picker/picker.js?owner530');
  const job={state:'running',progress:25,elapsed_seconds:120,remaining_seconds:null};
  const ru=picker.remainingTime(job,true,0,'ru');
  assert.match(ru,/Примерно до конца подбора: 6 мин/);
  assert.doesNotMatch(ru,/предел|лимит|остановк/);
  assert.match(picker.remainingTime(job,true,60,'en'),/about 5 min/i);
  assert.match(picker.remainingTime({...job,progress:0},true,0,'ru'),/первых проверок/);
  assert.equal(picker.remainingTime(job,false,0,'ru'),'');
});

test('A long planning estimate does not impose an overall generation cutoff',async()=>{
  const {planSelection,validPoolPlan}=await import('../webui/web/public/strategy-picker/concurrency.js');
  const selection=planSelection({search:'synthesis',extended:false,goal:'all',custom:null,requested:'100'});
  const plan={available:true,version:'picker-start-plan-v1',plan_sha256:'a'.repeat(64),selection,
    concurrency_choice:{policy_version:'picker-concurrency-v1',requested:'100',effective:100},
    budget:{concurrency:100,deadline_seconds:20000,cores:4,available_kib:2000000,load:0}};
  assert.equal(validPoolPlan(plan,selection),true);
  assert.equal(validPoolPlan({...plan,budget:{...plan.budget,deadline_seconds:NaN}},selection),false);
});


test('Recovered fixed stop permits a new UI request only when the server verified archival',async()=>{
  for(const can_restart of [false,true])await withUi(async ui=>{
    assert.equal(ui.nodes.get('start').disabled,!can_restart);
    await ui.click('start');
    assert.equal(ui.requests.some(p=>p.cmd==='pickerplan'),can_restart);
  },{job:{...report(),state:'recovery_required',phase:'recovery_required',restored:true,can_restart,code:'recovery_required'}});
});

test('User stop and process failures have distinct plain labels',async()=>{
  const {jobView}=await import('../webui/web/public/strategy-picker/picker.js');
  assert.equal(jobView({state:'cancelled'},'ru').phase,'Остановлен пользователем.');
  for(const state of ['failed','interrupted','recovery_required'])assert.notEqual(jobView({state},'ru').phase,'Остановлен пользователем.');
});


test('Ten custom targets survive preview, comparison and plan; an eleventh is refused',()=>{
  const hosts=Array.from({length:10},(_,i)=>`host${i}.example.com`);
  assert.ok(customScope(hosts,true,'all','ru'));
  assert.equal(planSelection({search:'synthesis',extended:false,goal:'all',custom:{hosts,only:true},requested:'2500'}).custom_hosts.length,10);
  assert.equal(customScope([...hosts,'extra.example.com'],true,'all','ru'),null);
});

test('JSON report is hidden during active selection and available after terminal publication',async()=>{
  const job={id:'a'.repeat(32),state:'running',phase:'discovering',restored:false,profiles:[],budget:{cores:4,available_kib:3000000,concurrency:10},search:'synthesis',goal:'all',concurrency:'auto'};
  await withUi(async ui=>{assert.equal(ui.nodes.get('download').hidden,true);});
  await withUi(async ui=>{
    assert.equal(ui.nodes.get('download').hidden,true);
    await ui.update({active:false,job:{...job,state:'completed',phase:'complete',restored:true}});
    assert.equal(ui.nodes.get('download').hidden,false);
  },{job});
});


test('Availability button hands off canonical targets without starting selection',async()=>{
  const hosts=Array.from({length:10},(_,i)=>`host${i}.example.com`);
  await withUi(async ui=>{
    ui.set('custom-enabled',{checked:true});ui.set('custom-sites',{value:hosts.join('\n')});
    await ui.click('custom-check');
    assert.deepEqual(JSON.parse(ui.stored.get('nfqws-site-check-targets-v1')),hosts);
    assert.deepEqual(ui.navigation,['/?site-check=1']);
    assert.equal(ui.requests.filter(p=>p.cmd==='pickertargets').length,1);
    assert.equal(ui.requests.some(p=>['pickersynthesize','pickerstart','dpisitecheck'].includes(p.cmd)),false);
  },{preview:()=>({valid:true,hosts,errors:[]})});
});


test('Final assembled pass-through is named explicitly and repeated runs are explained',async()=>{
  const picker=await import('../webui/web/public/strategy-picker/picker.js');
  const final={name:'Собранная стратегия · повторная проверка',source:'synthesis',components:{http:{method:'pass'},tls:{method:'pass'},quic:{method:'pass'},overrides:[]}};
  assert.match(picker.profileLabel(final,'ru'),/Собранная.*без методов обхода/);
  const active={...final,components:{...final.components,tls:{method:'multisplit'}}};
  assert.doesNotMatch(picker.profileLabel(active,'ru'),/без методов обхода/);
  assert.match(picker.retryHint('ru'),/второй, третий/);
  assert.match(picker.retryHint('ru'),/не гарантируется/);
  assert.match(picker.retryHint('en'),/second, third/);
});

test('Preselected sequential run count is consent-bound and cannot change after planning',async()=>{
  await withUi(async ui=>{
    ui.set('rounds-value',{value:'3'});ui.fire('rounds-value','input');
    await ui.click('start');
    assert.equal(ui.requests.find(p=>p.cmd==='pickerplan').rounds,'3');
    assert.match(ui.nodes.get('confirmation-text').textContent,/Прогонов подряд: 3/);
    ui.set('rounds-value',{value:'2'});ui.fire('rounds-value','input');
    assert.equal(ui.nodes.get('confirmation').hidden,true);
    assert.equal(ui.requests.some(p=>p.cmd==='pickersynthesize'),false);
    await ui.click('start');await ui.click('confirm-submit');
    assert.equal(ui.requests.find(p=>p.cmd==='pickersynthesize').rounds,'2');
  });
});


test('Owner682 new generation defaults to two confirmed sequential rounds',async()=>{
  await withUi(async ui=>{
    assert.equal(ui.nodes.get('rounds-value').value,'2');
    await ui.click('start');assert.equal(ui.nodes.get('confirmation').hidden,false);
    assert.equal(ui.requests.find(p=>p.cmd==='pickerplan').rounds,'2');
    await ui.click('confirm-submit');assert.equal(ui.requests.find(p=>p.cmd==='pickersynthesize').rounds,'2');
  });
});
test('Owner682 one round cannot acquire a new generation plan or confirmation',async()=>{
  await withUi(async ui=>{
    ui.set('rounds-value',{value:'1'});ui.fire('rounds-value','input');
    assert.match(ui.nodes.get('rounds-error').textContent,/2.*10/);
    await ui.click('start');assert.equal(ui.nodes.get('confirmation').hidden,true);
    assert.equal(ui.requests.some(p=>p.cmd==='pickerplan'||p.cmd==='pickersynthesize'),false);
  });
});
test('Owner684 million numeric selection reaches confirmation and request without router model references',async()=>{
  await withUi(async ui=>{
    ui.set('pool-value',{value:'1000000'});ui.fire('pool-value','input');
    assert.equal(ui.nodes.get('pool-value').value,'1000000');
    await ui.click('start');assert.equal(ui.requests.find(p=>p.cmd==='pickerplan').concurrency,'1000000');
    await ui.click('confirm-submit');assert.equal(ui.requests.find(p=>p.cmd==='pickersynthesize').concurrency,'1000000');
    const visible=[...ui.nodes.values()].map(n=>n.textContent||'').join(' ');assert.doesNotMatch(visible,/RT-AC87U|GT-BE19000AI/);
  });
});


test('All services checks every service and restores all four after a selected subset',async()=>{
  await withUi(async ui=>{
    const services=['youtube','discord','instagram','torrents'];
    for(const service of services){assert.equal(ui.nodes.get('goal-'+service).checked,true,service);assert.equal(ui.nodes.get('goal-'+service).disabled,true,service);}
    ui.set('goal-all',{checked:false});ui.set('goal-selected',{checked:true});await ui.fire('goal-selected','change');
    for(const service of services.slice(1))ui.set('goal-'+service,{checked:false});
    ui.set('goal-all',{checked:true});ui.set('goal-selected',{checked:false});await ui.fire('goal-all','change');
    for(const service of services)assert.equal(ui.nodes.get('goal-'+service).checked,true,service);
  });
});

test('All services displays measured ranges for each service and labels missing historical cells',async()=>{
  const job=report();delete job.custom_hosts;delete job.custom_only;job.state='failed';job.code='detector_failed';
  for(const profile of job.profiles)profile.runs.forEach((run,i)=>{run.services=Object.fromEntries(['youtube','discord','instagram','torrents'].map(s=>[s,Object.fromEntries(['http','tls12','tls13','quic'].map(k=>[k,{ok:i+1,total:2}]))]));});
  delete job.profiles[0].runs[0].services.instagram;
  await withUi(async ui=>{
    const rows=ui.nodes.get('results').childNodes;assert.equal(rows.length,2);
    const section=(row,tag)=>row.childNodes.find(n=>n.tagName==='table').childNodes.find(n=>n.tagName===tag);
    const serviceRows=section(rows[1],'tbody').childNodes;
    assert.deepEqual(serviceRows.map(row=>row.childNodes[0].textContent),['YouTube','Discord','Instagram','Торрент-трекеры']);
    const headers=section(rows[1],'thead').childNodes[0].childNodes.map(cell=>cell.textContent);
    const tls12=headers.indexOf('TLS 1.2');
    assert.notEqual(tls12,-1);
    for(const row of serviceRows)assert.equal(row.childNodes[tls12].textContent,'1–2/2');
    const missing=section(rows[0],'tbody').childNodes.find(row=>row.childNodes[0].textContent==='Instagram');
    assert.equal(missing.childNodes[1].textContent,'Нет замеров');
    assert.equal(ui.nodes.get('error').textContent,'DPI Detector не завершил измерение. Сохраните отчёт.');
    assert.equal(ui.nodes.get('apply').hidden,true);
  },{job});
});
