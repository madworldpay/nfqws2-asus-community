import assert from 'node:assert/strict';
import {test} from 'node:test';
import {cpuPercent, MetricsHistory, PickerStatusPoller} from '../webui/web/public/strategy-picker/metrics.js';

const a={boot:'a'.repeat(64),uptime_seconds:100,cpu_counters:[100,20,30,400,50,6,7,8],memory:{total_kib:131072,available_kib:70000,used_kib:61072,estimated:false},temperatures:[{sensor:'cpu-thermal',kind:'cpu',celsius:62.5}]};
const b={...a,uptime_seconds:108,cpu_counters:[140,20,40,430,60,6,17,8]};

test('CPU uses counter deltas across all cores, excluding idle and I/O wait',()=>{
  // Hand counted: total +100, idle+iowait +40 => 60% active.
  assert.equal(cpuPercent(a,b),60);
  assert.equal(cpuPercent({...a,cpu_counters:[4294967297,0,0,0,0,0,0,0]}, {...b,cpu_counters:[4294967397,0,0,100,0,0,0,0]}),50);
});

test('CPU cannot cross reboot, stale/reversed intervals or decreasing counters',()=>{
  for(const bad of [{...b,boot:'b'.repeat(64)},{...b,boot:null},{...b,uptime_seconds:100},
    {...b,uptime_seconds:99},{...b,uptime_seconds:140},{...b,cpu_counters:[140,20,40,430,49,6,17,8]},
    {...b,cpu_counters:null},{...b,cpu_counters:[Infinity,0,0,0,0,0,0,0]}])assert.equal(cpuPercent(a,bad),null);
  assert.equal(cpuPercent(a,a),null);
  assert.equal(cpuPercent(null,b),null);
});

test('Metrics show independent unknown fields, actual available RAM and identified temperature',()=>{
  const h=new MetricsHistory();h.accept(a,0);
  assert.match(h.view(0,'en').cpu,/collecting/i);
  h.accept(b,8000);const v=h.view(9000,'en');
  assert.equal(v.cpu,'CPU · 60%');
  assert.match(v.memory,/68\.4.*128\.0.*MiB/);
  assert.match(v.temperature,/CPU.*62\.5/);
  assert.match(v.freshness,/1 s/);
  h.accept({...b,uptime_seconds:109,memory:null,temperatures:[]},10000);
  assert.match(h.view(10000,'en').memory,/unavailable/);
  assert.equal(h.view(10000,'en').temperature,'');
});

test('Estimated RAM is explicit in both languages and stale data is never fresh',()=>{
  const h=new MetricsHistory();h.accept({...a,memory:{...a.memory,estimated:true}},0);
  assert.match(h.view(0,'ru').memory,/приблизительно/);
  assert.match(h.view(0,'en').memory,/estimated/);
  assert.equal(h.view(21000,'en').stale,true);
  assert.match(h.view(21000,'ru').freshness,/устарели/);
  assert.match(h.view(21000,'en').cpu,/unavailable/);
});

test('Unsupported CPU is unavailable immediately instead of promising two samples',()=>{
  const h=new MetricsHistory();h.accept({boot:null,uptime_seconds:100,cpu_counters:null,memory:null,temperatures:[]},0);
  assert.equal(h.view(0,'en').cpu,'CPU · unavailable');
  assert.equal(h.view(0,'ru').cpu,'Процессор · недоступно');
});

test('CPU never coerces null, strings or negative uptime into a fresh percentage',()=>{
  for(const value of [null,'0',-1,NaN,Infinity]){
    const first={...a,uptime_seconds:value},next={...b,uptime_seconds:8};
    assert.equal(cpuPercent(first,next),null);
    assert.equal(cpuPercent(next,first),null);
    const h=new MetricsHistory();h.accept(first,0);
    assert.equal(h.view(0,'en').cpu,'CPU · unavailable');
    h.accept(next,8000);assert.notEqual(h.view(8000,'en').cpu,'CPU · 60%');
    h.accept({...b,uptime_seconds:16,cpu_counters:[180,20,50,460,70,6,27,8]},16000);
    assert.equal(h.view(16000,'en').cpu,'CPU · 60%');
  }
});

test('A slow response includes delivery time in the conservative freshness window',async t=>{
  let now=0;t.mock.method(performance,'now',()=>now);
  const h=new MetricsHistory();let finish;
  const pending=h.request(()=>new Promise(resolve=>{finish=resolve;}));
  now=14000;finish({metrics:a});await pending;
  assert.equal(h.view(19000,'en').stale,false);
  assert.equal(h.view(24000,'en').stale,true);
  assert.match(h.view(19000,'en').freshness,/19 s/);
});

test('A request invalidated by hide or action cannot overwrite metrics or page data',async()=>{
  const h=new MetricsHistory();let finish,current=true;
  const pending=h.request(()=>new Promise(resolve=>{finish=resolve;}),()=>current);
  current=false;finish({metrics:a,job:{state:'running'}});
  assert.equal(await pending,null);
  assert.match(h.view(100,'en').freshness,/Waiting/);
});

test('Resume resets CPU window and an older response cannot replace a newer sample',()=>{
  const h=new MetricsHistory();h.accept(a,0);h.accept(b,8000);h.accept(a,9000);
  assert.equal(h.view(9000,'en').cpu,'CPU · 60%');
  h.pause();h.accept({...b,uptime_seconds:116,cpu_counters:[180,20,50,460,70,6,27,8]},16000);
  assert.match(h.view(16000,'en').cpu,/collecting/i);
  assert.match(h.view(16000,'ru').freshness,/0 с/);
});

class Visibility extends EventTarget{
  hidden=false;
  set(value){this.hidden=value;this.dispatchEvent(new Event('visibilitychange'));}
}

test('Visible poller never overlaps requests or continues polling while hidden',async t=>{
  t.mock.timers.enable({apis:['setInterval']});
  const doc=new Visibility();let calls=0,ticks=0,paused=0,release;
  const p=new PickerStatusPoller(doc,()=>{calls++;return new Promise(r=>{release=r;});},()=>ticks++,()=>paused++);
  p.start();assert.equal(calls,1);
  t.mock.timers.tick(24000);assert.equal(calls,1);assert.ok(ticks>=3);
  doc.set(true);const was=ticks;t.mock.timers.tick(24000);assert.equal(ticks,was);assert.equal(paused,1);
  release();await Promise.resolve();await Promise.resolve();
  doc.set(false);assert.equal(calls,2);
  release();await Promise.resolve();await Promise.resolve();
  t.mock.timers.tick(8000);assert.equal(calls,3);
  p.stop();release();await Promise.resolve();
  const stopped=ticks;t.mock.timers.tick(24000);doc.set(true);doc.set(false);assert.equal(calls,3);assert.equal(ticks,stopped);
});

test('Polling resumes after a rejected status and tolerates stop while request pending',async t=>{
  t.mock.timers.enable({apis:['setInterval']});
  const doc=new Visibility();let calls=0;const p=new PickerStatusPoller(doc,async()=>{calls++;throw new Error('offline');});
  p.start();await Promise.resolve();await Promise.resolve();
  t.mock.timers.tick(8000);assert.equal(calls,2);p.stop();
  await Promise.resolve();await Promise.resolve();t.mock.timers.tick(16000);assert.equal(calls,2);
});
