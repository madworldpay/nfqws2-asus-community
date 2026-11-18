import assert from 'node:assert/strict';
import {test} from 'node:test';
import {existsSync,readFileSync} from 'node:fs';
const moduleURL=new URL('../webui/web/public/strategy-picker/supplement.js',import.meta.url);
const api=existsSync(moduleURL)?await import(moduleURL.href):{};
const sha=n=>n.repeat(64),binding={config_sha256:sha('a'),resources_sha256:sha('b')};
const recipe=()=>({http:{method:'pass'},tls:{method:'multisplit',pos:'1,midsld'},quic:{method:'fake',repeats:2},overrides:[]});
function job(){return {id:'1'.repeat(32),search:'synthesis',state:'completed',restored:true,generated:'new:s-final',winner:'old',profiles:[
 {id:'old',source:'current',sample_type:'repeated',rank:{reason:'baseline'}},
 {id:'new',recipe:'s-final',source:'synthesis',sample_type:'repeated',components:recipe()}]};}
const off=()=>({can_apply:false,can_export:false,combined_verified:false,actual_device_calls:false});
const saved=()=>({mode:'supplement-saved-state-v1',binding:structuredClone(binding),saved_config_bound:true,...off()});
function proposal(domains=['example.com']){return {mode:'supplement-saved-preview-v1',binding:structuredClone(binding),saved_config_bound:true,...off(),preview_sha256:sha('c'),proposal:{
 mode:'supplement-current-resource-proposal-v1',resource_inventory_bound:true,resources_bundled:true,config_source_proved:false,...off(),proposal_sha256:sha('d'),resource_kit_sha256:sha('e'),
 preview:{mode:'supplement-current-preview-v1',base_sha256:binding.config_sha256,resources_sha256:binding.resources_sha256,candidate_sha256:sha('f'),recipe:recipe(),domains,
 changed_keys:['NFQWS_ARGS_CUSTOM'],added_profiles:['--filter-tcp=443 --hostlist-domains=example.com --lua-desync=multisplit:pos=1,midsld'],...off(),resources_bundled:false,resource_inventory_proved:false},
 resource_kit:{schema_version:1,complete:true,files:[{path:'/opt/etc/nfqws2/lua/zapret-lib.lua',kind:'lua',sha256:sha('a'),byte_length:1,data_base64:'YQ=='}]}}};}
function controller(request){assert.equal(typeof api.SupplementPreview,'function','read-only supplement controller required');
 const context={available:true,job:job(),domains:'example.com'},calls=[];
 const c=new api.SupplementPreview({context:()=>context,request:async(cmd,extra)=>{calls.push({cmd,extra});return request?await request(cmd,extra):cmd==='importsupplementstate'?saved():proposal();}});
 return {c,context,calls};}
const defer=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};

test('Uses the unique completed generated recipe, not the winner or an arbitrary profile',()=>{
 assert.equal(typeof api.supplementSource,'function');const j=job(),s=api.supplementSource(j);
 assert.deepEqual(s.recipe,recipe());assert.ok(s.key.includes(j.id));assert.notEqual(j.generated,j.winner);
 s.recipe.tls.method='pass';assert.equal(j.profiles[1].components.tls.method,'multisplit');
});
test('Unsupported scoped recipes are refused whole rather than silently dropping overrides',()=>{
 assert.equal(typeof api.supplementSource,'function');
 for(const change of [j=>j.state='running',j=>j.restored=false,j=>j.search='profiles',j=>j.generated='missing',j=>j.profiles.push(j.profiles[1]),
 j=>j.profiles[1].source='catalog',j=>j.profiles[1].sample_type='exploratory',j=>j.profiles[1].error='failed',
 j=>j.profiles[1].components.overrides=[{domains:['other.example.com']}],j=>j.profiles[1].components.custom_scope={only:true},
 j=>j.profiles[1].components.quic={method:'pass'},j=>j.profiles[1].components.tls={method:'pass'},j=>j.profiles[1].components=recipe().tls]){
  const j=job();change(j);
  // Individual pass protocols are supported; an all-pass recipe is not.
  if(j.profiles[1]?.components?.tls?.method==='pass'&&j.profiles[1]?.components?.quic?.method==='fake')j.profiles[1].components.quic={method:'pass'};
  else if(j.profiles[1]?.components?.quic?.method==='pass'&&j.profiles[1]?.components?.tls?.method==='multisplit')j.profiles[1].components.tls={method:'pass'};
  assert.equal(api.supplementSource(j),null);
 }
});
test('Domain entry is explicit, bounded, canonical and excludes IPs, URLs and Telegram',()=>{
 assert.equal(typeof api.supplementDomains,'function');assert.deepEqual(api.supplementDomains(' B.example.com\n\na.example.com '),['a.example.com','b.example.com']);
 for(const value of ['', 'a.com\na.com','a.com\nb.com\nc.com\nd.com\ne.com\nf.com','https://example.com/','8.8.8.8','a.com:443',
 't.me','a.telegram.org','foo bar.com','<img src=x>','ümlaut.de','a'.repeat(4097)])assert.equal(api.supplementDomains(value),null,value);
});
test('One explicit preview obtains fresh binding then sends only recipe, domains and the two CAS hashes',async()=>{
 const {c,calls}=controller();await c.prepare();assert.equal(c.view.phase,'ready');assert.equal(calls.length,2);
 assert.deepEqual(calls[0],{cmd:'importsupplementstate',extra:{}});
 assert.deepEqual(calls[1],{cmd:'importsupplementpreview',extra:{recipe:JSON.stringify(recipe()),domains:'["example.com"]',...binding}});
 assert.equal(c.view.preview.added_profiles.length,1);assert.equal(c.view.preview.files.length,1);
 assert.equal('candidate_config'in c.view.preview,false);assert.equal('data_base64'in c.view.preview.files[0],false);
});
test('Malformed or authority-bearing state refuses before a preview RPC',async()=>{
 for(const change of [s=>s.can_apply=true,s=>delete s.actual_device_calls,s=>s.saved_config_bound=false,s=>s.binding.config_sha256='old',s=>s.mode='other']){
  const {c,calls}=controller(()=>{const s=saved();change(s);return s;});await c.prepare();assert.equal(c.view.phase,'error');assert.equal(calls.length,1);assert.equal(c.view.preview,null);
 }
});
test('Report changes during state IO prevent any second request',async()=>{
 const d=defer(),{c,calls,context}=controller(()=>d.promise);const p=c.prepare();context.job.id='2'.repeat(32);d.resolve(saved());await p;
 assert.equal(calls.length,1);assert.equal(c.view.preview,null);assert.notEqual(c.view.phase,'ready');
});
test('Changed domains or availability discard a delayed preview response',async()=>{
 for(const change of [x=>x.domains='new.example.com',x=>x.available=false,x=>x.job.profiles[1].components.tls.pos='host+1']){
  const d=defer(),{c,context}=controller(cmd=>cmd==='importsupplementstate'?saved():d.promise);const p=c.prepare();await Promise.resolve();await Promise.resolve();change(context);d.resolve(proposal());await p;
  assert.equal(c.view.preview,null);assert.notEqual(c.view.phase,'ready');
 }
});
test('Page invalidation discards in-flight output and never retries automatically',async()=>{
 const d=defer(),{c,calls}=controller(()=>d.promise);const p=c.prepare();c.invalidate();d.resolve(saved());await p;
 assert.equal(calls.length,1);assert.equal(c.view.preview,null);
});
test('Double click cannot issue another state read while the original request is pending',async()=>{
 const d=defer(),{c,calls}=controller(cmd=>cmd==='importsupplementstate'?d.promise:proposal());const p=c.prepare();await c.prepare();assert.equal(calls.length,1);d.resolve(saved());await p;assert.equal(calls.length,2);
});
test('Response scope, bindings, exact additions and complete resource kit are required without promoting operational flags',async()=>{
 for(const change of [p=>p.binding.resources_sha256=sha('c'),p=>p.can_export=true,p=>p.proposal.can_apply=true,p=>p.proposal.preview.combined_verified=true,
 p=>p.proposal.preview.domains=['other.com'],p=>p.proposal.preview.recipe.tls.pos='midsld',p=>p.proposal.preview.base_sha256=sha('c'),
 p=>p.proposal.preview.changed_keys=['NFQWS_ARGS'],p=>p.proposal.preview.added_profiles=[],p=>p.proposal.resource_kit.complete=false,
 p=>p.proposal.resource_kit.files[0].byte_length=262145,p=>p.proposal.resource_kit.files[0].path='/opt/etc/nfqws2/../secret',
 p=>p.proposal.resource_kit.files.push(p.proposal.resource_kit.files[0])]){
  const {c}=controller(cmd=>{if(cmd==='importsupplementstate')return saved();const p=proposal();change(p);return p;});await c.prepare();assert.equal(c.view.phase,'error');assert.equal(c.view.preview,null);
 }
});
test('A later refusal clears the old preview; an explicit second attempt uses a new state read',async()=>{
 let fail=false;const {c,calls}=controller(cmd=>{if(cmd==='importsupplementstate')return saved();if(fail)throw new Error('source_changed');return proposal();});
 await c.prepare();assert.equal(c.view.phase,'ready');fail=true;await c.prepare();assert.equal(c.view.phase,'error');assert.equal(c.view.preview,null);assert.equal(calls.filter(x=>x.cmd==='importsupplementstate').length,2);
});

function dom(){const nodes=new Map(),element=()=>({hidden:false,disabled:false,checked:false,value:'',textContent:'',childNodes:[],listeners:new Map(),classList:{toggle(){}},
 append(v){this.childNodes.push(v);},replaceChildren(){this.childNodes=[];},addEventListener(t,f){this.listeners.set(t,f);}});
 return {nodes,document:{hidden:false,documentElement:{lang:'ru'},addEventListener(){},removeEventListener(){},createElement:element,getElementById(id){if(!nodes.has(id))nodes.set(id,element());return nodes.get(id);}}};}
test('RU/EN view renders literal additions and file names, and exposes no Apply or export action',async()=>{
 assert.equal(typeof api.mountSupplement,'function');const {document,nodes}=dom();let language='ru';
 const p=proposal();p.proposal.preview.added_profiles=['<img src=x onerror=alert(1)>'];
 const ui=api.mountSupplement({document,context:()=>({available:true,job:job()}),language:()=>language,request:async cmd=>cmd==='importsupplementstate'?saved():p});ui.render();
 const fire=(id,type='click')=>nodes.get(id).listeners.get(type)();await fire('supplement-open');nodes.get('supplement-domains').value='example.com';await fire('supplement-submit');
 assert.equal(nodes.get('supplement-rules').textContent,'<img src=x onerror=alert(1)>');assert.equal(nodes.get('supplement-files').childNodes[0].textContent,'/opt/etc/nfqws2/lua/zapret-lib.lua (1 B)');
 assert.match(nodes.get('supplement-note').textContent,/повторн/);assert.match(nodes.get('supplement-submit').textContent,/Предпросмотр/);
 language='en';ui.render();assert.match(nodes.get('supplement-note').textContent,/repeat/i);assert.match(nodes.get('supplement-submit').textContent,/Preview/);
 assert.equal(nodes.get('supplement-rules').innerHTML,undefined);assert.deepEqual([...nodes].filter(([id,n])=>id.startsWith('supplement-')&&n.listeners.has('click')).map(([id])=>id).sort(),['supplement-open','supplement-submit']);
});
test('Actual picker wires the existing same-origin API, drops preview on busy state/auth expiry/pagehide and has accessible HTML controls',async()=>{
 const previous=Object.fromEntries(['document','window','fetch','sessionStorage'].map(k=>[k,globalThis[k]]));const {document,nodes}=dom(),events=new Map(),calls=[];let state={active:false,job:job(),detector:{installed:true},error:null},denyPreview=false;
 globalThis.document=document;globalThis.window={addEventListener:(k,v)=>events.set(k,v)};globalThis.sessionStorage={getItem:()=>null,setItem(){},removeItem(){}};
 globalThis.fetch=async(url,options)=>{assert.equal(url,'/index.php');assert.equal(options.credentials,'same-origin');const x=Object.fromEntries(options.body);calls.push(x);
  if(denyPreview&&x.cmd==='importsupplementpreview')return {ok:false,status:401,json:async()=>({error:'auth'})};
  const v=x.cmd==='status'?{csrf_token:'test-session'}:x.cmd==='pickerstatus'?state:x.cmd==='importsupplementstate'?saved():proposal();return {ok:true,status:200,json:async()=>structuredClone(v)};};
 const tick=()=>new Promise(r=>setImmediate(r)),fire=async(id,t='click')=>{await nodes.get(id)?.listeners.get(t)?.();await tick();};
 try{await import('../webui/web/public/strategy-picker/picker.js?supplement-new-test');await tick();await tick();
  assert.equal(typeof nodes.get('supplement-open')?.listeners.get('click'),'function','picker must wire the explicit supplement action');
  await fire('supplement-open');nodes.get('supplement-domains').value='example.com';await fire('supplement-submit');
  assert.equal(calls.filter(x=>x.cmd==='importsupplementpreview').length,1);assert.ok(calls.filter(x=>x.cmd.startsWith('importsupplement')).every(x=>x.csrf_token==='test-session'));
  assert.equal(nodes.get('supplement-output').hidden,false);state={...state,active:true};await fire('refresh');assert.equal(nodes.get('supplement-output').hidden,true);
  state={...state,active:false};await fire('refresh');await fire('supplement-open');denyPreview=true;await fire('supplement-submit');
  assert.equal(nodes.get('supplement-section').hidden,true);assert.equal(nodes.get('supplement-output').hidden,true);
  assert.equal(calls.filter(x=>x.cmd==='importsupplementpreview').length,2,'401 must not replay the preview');events.get('pagehide')();
  assert.ok(calls.every(x=>['status','pickerstatus','importsupplementstate','importsupplementpreview'].includes(x.cmd)));
  const html=readFileSync(new URL('../webui/web/public/strategy-picker/index.html',import.meta.url),'utf8');assert.match(html,/for="supplement-domains"/);assert.match(html,/id="supplement-error" role="alert"/);assert.match(html,/id="supplement-output"[^>]*aria-live="polite"/);
 }finally{events.get('pagehide')?.();for(const [k,v]of Object.entries(previous)){if(v===undefined)delete globalThis[k];else globalThis[k]=v;}}
});
