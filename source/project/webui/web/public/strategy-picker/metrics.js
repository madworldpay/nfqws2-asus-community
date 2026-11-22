// Aggregate /proc/stat deltas include the generator, Detector, NFQWS and the OS.
// There is deliberately no process-name RSS/CPU filter or guessed thread cost.
const validClock=sample=>sample&&typeof sample.boot==='string'&&/^[a-f0-9]{64}$/.test(sample.boot)&&Number.isFinite(sample.uptime_seconds)&&sample.uptime_seconds>=0;
const validCounters=a=>Array.isArray(a)&&a.length===8&&a.every(n=>Number.isSafeInteger(n)&&n>=0);
export function cpuPercent(before,after){
  if(!validClock(before)||!validClock(after)||before.boot!==after.boot)return null;
  const seconds=after.uptime_seconds-before.uptime_seconds;
  if(!Number.isFinite(seconds)||seconds<0.25||seconds>30)return null;
  if(!validCounters(before.cpu_counters)||!validCounters(after.cpu_counters))return null;
  const delta=after.cpu_counters.map((n,i)=>n-before.cpu_counters[i]);
  if(delta.some(n=>n<0))return null; // iowait may decrease; start a new window.
  const total=delta.reduce((a,b)=>a+b,0);
  if(!Number.isSafeInteger(total)||total<=0)return null;
  return Math.round((total-delta[3]-delta[4])*100/total);
}

export class MetricsHistory{
  sample=null;previous=null;received=null;discontinuity=false;
  async request(fetcher,isCurrent=()=>true){
    // No synchronized router/browser clock is assumed. Starting at request
    // dispatch conservatively includes the full delivery delay in data age.
    const started=performance.now(),result=await fetcher();
    if(!isCurrent())return null;
    this.accept(result.metrics,started);return result;
  }
  accept(sample,now){
    if(!sample||typeof sample!=='object')return;
    if(validClock(this.sample)&&validClock(sample)&&sample.boot===this.sample.boot&&sample.uptime_seconds<=this.sample.uptime_seconds)return;
    this.previous=this.discontinuity?null:this.sample;this.sample=sample;this.received=now;this.discontinuity=false;
  }
  pause(){this.previous=null;this.discontinuity=true;}
  view(now,language='ru'){
    const ru=language==='ru',unknown=ru?'недоступно':'unavailable',age=this.received===null?null:now-this.received;
    const stale=age===null||!Number.isFinite(age)||age<0||age>20000;
    const percent=stale?null:cpuPercent(this.previous,this.sample);
    const canCollect=validClock(this.sample)&&validCounters(this.sample.cpu_counters);
    const cpu=(ru?'Процессор · ':'CPU · ')+(percent!==null?percent+'%':!stale&&!this.previous&&canCollect?(ru?'измеряем загрузку':'collecting two samples'):unknown);
    const m=this.sample?.memory;
    const valid=m&&[m.total_kib,m.available_kib,m.used_kib].every(n=>Number.isSafeInteger(n)&&n>=0)&&m.total_kib>0&&m.available_kib<=m.total_kib&&m.used_kib===m.total_kib-m.available_kib;
    const mib=n=>(n/1024).toFixed(1);
    const memory=valid?(ru?`Память · доступно ${mib(m.available_kib)} из ${mib(m.total_kib)} МиБ; занято ${mib(m.used_kib)} МиБ`:`RAM · available ${mib(m.available_kib)} of ${mib(m.total_kib)} MiB; used ${mib(m.used_kib)} MiB`)+(m.estimated?(ru?' · приблизительно':' · estimated'):''):(ru?'Память · ':'RAM · ')+unknown;
    const sensors=Array.isArray(this.sample?.temperatures)?this.sample.temperatures.filter(s=>['cpu','soc'].includes(s?.kind)&&/^[a-z0-9_-]{1,32}$/.test(s.sensor)&&Number.isFinite(s.celsius)&&s.celsius>=-20&&s.celsius<=150).slice(0,4):[];
    const temperature=sensors.length?sensors.map(s=>`${ru?(s.kind==='cpu'?'Температура процессора':'Температура чипа'):(s.kind==='cpu'?'CPU temperature':'Chip temperature')} · ${s.celsius.toFixed(1)} °C`).join(' · '):'';
    const freshness=age===null?(ru?'Ожидаем данные роутера.':'Waiting for router data.'):stale?(ru?'Данные устарели. Нажмите «Обновить состояние», чтобы проверить снова.':'Data is stale. Select “Refresh status” to check again.'):(ru?`Данные роутера обновлены ${Math.floor(age/1000)} с назад.`:`Router data updated ${Math.floor(age/1000)} s ago.`);
    return {cpu,memory,temperature,freshness,stale};
  }
}

/** Reuse one visible-only status request, including manual refresh. */
export class PickerStatusPoller{
  running=false;pending=false;timer=null;
  constructor(document,refresh,tick=()=>{},pause=()=>{}){
    this.document=document;this.callback=refresh;this.tick=tick;this.pause=pause;
    this.changed=()=>{if(this.document.hidden){this.clear();this.pause();}else this.arm();};
  }
  clear(){if(this.timer!==null)clearInterval(this.timer);this.timer=null;}
  arm(){this.clear();this.timer=setInterval(()=>void this.refresh(),8000);void this.refresh();}
  start(){if(this.running)return;this.running=true;this.document.addEventListener('visibilitychange',this.changed);if(!this.document.hidden)this.arm();}
  stop(){if(!this.running)return;this.running=false;this.clear();this.document.removeEventListener('visibilitychange',this.changed);this.pause();}
  async refresh(){
    if(!this.running||this.document.hidden)return;
    this.tick();if(this.pending)return;this.pending=true;
    try{await this.callback();}catch{/* The page renders its own request error. */}
    finally{this.pending=false;if(this.running&&!this.document.hidden)this.tick();}
  }
}
