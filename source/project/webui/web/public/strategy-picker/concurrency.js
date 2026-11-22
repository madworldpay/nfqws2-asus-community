// These steps are input conveniences, not measured hardware limits.
import {customTargetIdentity} from './custom.js';
export function poolChoice(value){
  return typeof value==='string'&&(value==='auto'||/^[1-9][0-9]{0,6}$/.test(value)&&Number(value)<=1000000)?value:null;
}
export function roundChoice(value){
  return typeof value==='string'&&/^(?:[1-9]|10)$/.test(value)?Number(value):null;
}
export function poolDescription(choice,language='ru'){
  if(!choice||poolChoice(choice.requested)===null||!Number.isSafeInteger(choice.effective)||choice.effective<1||choice.effective>1000000||
    choice.requested!=='auto'&&Number(choice.requested)!==choice.effective)return null;
  return language==='ru'?`${choice.requested==='auto'?'Автоматически':'Вручную'} — до ${choice.effective} проверок одновременно для одной стратегии.`:
    `${choice.requested==='auto'?'Automatic':'Manual'} — up to ${choice.effective} simultaneous checks for one strategy.`;
}
export function recordedPool(job){
  if(job?.concurrency_valid===false)return null;
  if(job?.concurrency_choice!==undefined&&job.concurrency_choice!==null){
    const c=job.concurrency_choice;
    return c.policy_version==='picker-concurrency-v1'&&poolDescription(c)!==null&&c.effective===job?.budget?.concurrency?c:null;
  }
  const c={requested:'auto',effective:job?.budget?.concurrency};
  return poolDescription(c)===null?null:c;
}
export function planSelection({search,extended,goal,custom,requested,rounds=search==='synthesis'?'2':'1'}){
  if(poolChoice(requested)===null)return null;
  const count=roundChoice(rounds);if(count===null||search==='synthesis'&&count<2||search!=='synthesis'&&count!==1)return null;
  const s={search,extended,goal};if(requested!=='auto')s.concurrency=requested;
  if(count>1)s.rounds=count;
  if(custom){
    const targets=customTargetIdentity(custom.hosts);if(targets===null||typeof custom.only!=='boolean')return null;
    s.custom_hosts=[...custom.hosts].sort();s.custom_only=custom.only;
    if(targets.some(t=>t.kind==='ipv4')){
      s.custom_target_policy='custom-public-targets-v2';s.custom_targets=customTargetIdentity(s.custom_hosts);
    }
  }
  return s;
}
export function validPoolPlan(plan,selection){
  if(!plan||plan.available!==true||plan.version!=='picker-start-plan-v1'||!selection||
    !/^[a-f0-9]{64}$/.test(plan.plan_sha256||''))return false;
  const keys=Object.keys(selection).sort();
  if(!plan.selection||Object.keys(plan.selection).sort().join(',')!==keys.join(',')||
    keys.some(k=>JSON.stringify(selection[k])!==JSON.stringify(plan.selection[k])))return false;
  const c=plan.concurrency_choice,b=plan.budget;
  return c?.policy_version==='picker-concurrency-v1'&&c.requested===(selection.concurrency||'auto')&&
    poolDescription(c)!==null&&b?.concurrency===c.effective&&Number.isSafeInteger(b.deadline_seconds)&&
    b.deadline_seconds>0&&Number.isSafeInteger(b.cores)&&b.cores>0&&
    Number.isSafeInteger(b.available_kib)&&b.available_kib>=1&&Number.isFinite(b.load)&&b.load>=0;
}
