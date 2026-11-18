// Read-only preparation. This module never submits a trial, save, Apply or export.
const object=v=>v!==null&&typeof v==='object'&&!Array.isArray(v);
const hash=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const off=v=>object(v)&&['can_apply','can_export','combined_verified','actual_device_calls'].every(k=>v[k]===false);
const canonical=v=>JSON.stringify(v,(_,x)=>object(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
const same=(a,b)=>canonical(a)===canonical(b);

export function supplementSource(job){
  if(job?.state!=='completed'||job.restored!==true||job.search!=='synthesis'||typeof job.id!=='string'||
    !/^[a-f0-9]{32}$/.test(job.id)||typeof job.generated!=='string'||!Array.isArray(job.profiles))return null;
  const matches=job.profiles.filter(p=>object(p)&&p.id+':'+p.recipe===job.generated);
  if(matches.length!==1)return null;
  const p=matches[0],r=p.components;
  if(p.source!=='synthesis'||p.sample_type!=='repeated'||p.error||!object(r)||
    Object.keys(r).some(k=>!['http','tls','quic','overrides'].includes(k))||
    'overrides'in r&&(!Array.isArray(r.overrides)||r.overrides.length)||
    !['http','tls','quic'].every(k=>object(r[k])&&typeof r[k].method==='string')||
    ['http','tls','quic'].every(k=>r[k].method==='pass'))return null;
  const raw=JSON.stringify(r);if(raw.length>8192)return null;
  return {key:JSON.stringify([job.id,job.generated,r]),recipe:JSON.parse(raw)};
}
export function supplementDomains(raw){
  if(typeof raw!=='string'||raw.length>4096)return null;
  const domains=raw.split(/\r?\n/).map(s=>s.trim().toLowerCase()).filter(Boolean);
  if(!domains.length||domains.length>5||new Set(domains).size!==domains.length)return null;
  for(const host of domains){
    if(host.length>253||!/^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:[a-z]{2,63}|xn--[a-z0-9-]{1,59})$/.test(host)||
      ['t.me','telegram.org','telegram.me','telesco.pe'].some(x=>host===x||host.endsWith('.'+x)))return null;
  }
  return domains.sort(); // The server's existing compiler performs authoritative validation.
}
function stateBinding(v){
  if(v?.mode!=='supplement-saved-state-v1'||v.saved_config_bound!==true||!off(v)||
    !object(v.binding)||!hash(v.binding.config_sha256)||!hash(v.binding.resources_sha256))throw new Error('invalid_preview');
  return {config_sha256:v.binding.config_sha256,resources_sha256:v.binding.resources_sha256};
}
function previewView(v,binding,recipe,domains){
  const q=v?.proposal,p=q?.preview,k=q?.resource_kit;
  if(v?.mode!=='supplement-saved-preview-v1'||v.saved_config_bound!==true||!off(v)||!same(v.binding,binding)||!hash(v.preview_sha256)||
    q?.mode!=='supplement-current-resource-proposal-v1'||!off(q)||q.config_source_proved!==false||
    q.resource_inventory_bound!==true||q.resources_bundled!==true||!hash(q.proposal_sha256)||!hash(q.resource_kit_sha256)||
    p?.mode!=='supplement-current-preview-v1'||!off(p)||p.resources_bundled!==false||p.resource_inventory_proved!==false||
    p.base_sha256!==binding.config_sha256||p.resources_sha256!==binding.resources_sha256||!hash(p.candidate_sha256)||
    !same(p.recipe,recipe)||!same(p.domains,domains)||!same(p.changed_keys,['NFQWS_ARGS_CUSTOM'])||
    !Array.isArray(p.added_profiles)||!p.added_profiles.length||p.added_profiles.length>3||
    p.added_profiles.some(x=>typeof x!=='string'||!x.length||x.length>65536)||
    k?.schema_version!==1||k.complete!==true||!Array.isArray(k.files)||!k.files.length||k.files.length>128)throw new Error('invalid_preview');
  const paths=new Set();let total=0;
  const files=k.files.map(f=>{
    if(!object(f)||!['lists','lua','blobs'].includes(f.kind)||typeof f.path!=='string'||f.path.length>512||
      !f.path.startsWith('/opt/etc/nfqws2/'+f.kind+'/')||f.path.split('/').some((x,i)=>i>0&&(!/^[a-zA-Z0-9._-]+$/.test(x)||x==='.'||x==='..'))||
      paths.has(f.path)||!hash(f.sha256)||!Number.isSafeInteger(f.byte_length)||f.byte_length<0||f.byte_length>262144||typeof f.data_base64!=='string')throw new Error('invalid_preview');
    paths.add(f.path);total+=f.byte_length;return {path:f.path,byte_length:f.byte_length};
  });
  if(total>524288)throw new Error('invalid_preview');
  // Keep display fields only. Config and embedded resource bytes are neither
  // placed in the DOM nor persisted in the mutation/session-storage journal.
  return {domains:[...domains],added_profiles:[...p.added_profiles],files};
}
export class SupplementPreview{
  constructor({context,request,change=()=>{}}){this.context=context;this.request=request;this.change=change;this.epoch=0;this.key=null;this.pending=false;this.view={phase:'idle',preview:null,error:''};}
  sync(){
    const c=this.context(),source=c?.available===true?supplementSource(c.job):null;
    const key=source?JSON.stringify([source.key,c.domains]):null;
    if(this.key!==key){this.key=key;this.epoch++;this.view={phase:'idle',preview:null,error:''};}
    return source;
  }
  invalidate(){this.epoch++;this.key=null;this.view={phase:'idle',preview:null,error:''};}
  async prepare(){
    const source=this.sync();if(this.pending||!source)return;
    const domains=supplementDomains(this.context().domains);
    if(!domains){this.view={phase:'error',preview:null,error:'invalid_domains'};this.change();return;}
    const epoch=this.epoch,key=this.key,current=()=>{this.sync();return epoch===this.epoch&&key===this.key;};
    this.pending=true;this.view={phase:'loading',preview:null,error:''};this.change();
    try{
      const state=await this.request('importsupplementstate',{});if(!current())return;
      const binding=stateBinding(state);
      const result=await this.request('importsupplementpreview',{recipe:JSON.stringify(source.recipe),domains:JSON.stringify(domains),...binding});
      if(!current())return;
      this.view={phase:'ready',preview:previewView(result,binding,source.recipe,domains),error:''};
    }catch(e){if(current())this.view={phase:'error',preview:null,error:['source_changed','auth'].includes(e.message)?e.message:'invalid_preview'};}
    finally{this.pending=false;this.change();}
  }
}
const labels={
  ru:{open:'Дополнить текущую стратегию',title:'Предпросмотр дополнения',domains:'От одного до пяти доменов, каждый с новой строки',submit:'Предпросмотр дополнения',loading:'Подготовка предпросмотра…',
    help:'Правила собранного варианта будут предложены только для указанных доменов. Введите домены без адреса страницы и без IP. Telegram исключён.',
    additions:'Добавляемые правила',files:'Файлы полного комплекта',note:'Это предпросмотр: настройки ещё не сохранены. Объединённую стратегию нужно проверить повторно на тех же целях и контрольных сайтах. Применение и экспорт дополнения пока недоступны.',
    invalid_domains:'Введите от одного до пяти разных доменов без URL и IP. Домены Telegram исключены.',source_changed:'Настройки или файлы изменились. Подготовьте новый предпросмотр.',auth:'Сессия закончилась. Войдите в основную панель и обновите страницу.',invalid_preview:'Предпросмотр недоступен для этого варианта или текущих файлов. Настройки не сохранены.'},
  en:{open:'Supplement the current strategy',title:'Supplement preview',domains:'One to five domains, one per line',submit:'Preview supplement',loading:'Preparing preview…',
    help:'Propose rules from the generated candidate only for these domains. Enter domains without a page URL or IP address. Telegram is excluded.',
    additions:'Rules to add',files:'Complete kit files',note:'This is a preview; settings have not been saved. Repeat checks of the combined strategy with the same goals and control sites. Supplement Apply and export are not available yet.',
    invalid_domains:'Enter one to five distinct domains without URLs or IP addresses. Telegram domains are excluded.',source_changed:'Settings or files changed. Prepare a new preview.',auth:'Your session expired. Sign in on the main panel and reload this page.',invalid_preview:'A preview is unavailable for this candidate or the current files. Settings have not been saved.'}
};
export function mountSupplement({document,request,context,language}){
  const $=id=>document.getElementById('supplement-'+id);let opened=false,openedFor=null;
  const c=new SupplementPreview({context:()=>({...context(),domains:$('domains').value}),request,change:render});
  function render(){
    const source=c.sync(),w=labels[language()]||labels.ru;
    if(!source||source.key!==openedFor)opened=false;
    $('section').hidden=!source;$('form').hidden=!opened;
    for(const id of ['open','title','help','submit','note'])$(id).textContent=w[id];
    $('domains-label').textContent=w.domains;$('additions-title').textContent=w.additions;$('files-title').textContent=w.files;
    $('open').setAttribute?.('aria-expanded',String(opened));
    $('submit').disabled=c.pending||!source;$('domains').disabled=!source;
    if(c.pending)$('submit').textContent=w.loading;
    $('error').textContent=w[c.view.error]||'';
    const p=c.view.preview;$('output').hidden=!opened||!p;$('rules').textContent=p?p.added_profiles.join('\n--new\n'):'';
    $('scope').textContent=p?p.domains.join(', '):'';$('files').replaceChildren();
    if(p)for(const f of p.files){const li=document.createElement('li');li.textContent=f.path+' ('+f.byte_length+' B)';$('files').append(li);}
  }
  $('open').addEventListener('click',()=>{const source=c.sync();if(!source)return;opened=!opened;openedFor=source.key;if(!opened)c.invalidate();render();});
  $('domains').addEventListener('input',()=>{c.sync();render();});
  $('submit').addEventListener('click',()=>c.prepare());
  return {render,invalidate(){c.invalidate();render();}};
}
