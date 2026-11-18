import {MetricsHistory,PickerStatusPoller} from './metrics.js';
import {mountSupplement} from './supplement.js';
import {customMeasurements,customComparison,customScope,targetErrors,validTargetPreview} from './custom.js';
import {poolChoice,poolDescription,recordedPool,planSelection,validPoolPlan,roundChoice} from './concurrency.js';

export function addonNotice(job,language='ru'){
  if(job?.state!=='applied'||!job.torrent_sites)return '';
  return language==='ru'?'Добавлено дополнение «Торрент-трекеры». Показатели относятся к исходному комплекту без дополнения; после добавления повторите проверку.':'The tracker extension was added. The scores describe the base strategy before this extension; repeat the checks after adding it.';
}
export function jobView(job,language='ru'){
  const w=words[language],state=job?.state,finished=['completed','applied'].includes(state);
  const stopped=['failed','cancelled','interrupted','recovery_required'].includes(state);
  const phase=stopped?(w[state]||w.failed):(w[job?.phase]||job?.phase||'');
  const noWinner=stopped?(w[state]||w.failed):state==='applied'?w.applied:state==='completed'?
    (job.generation?.verified?(language==='ru'?'Исходная стратегия сохранена. Собранный комплект доступен для скачивания.':'Original retained. The generated kit is available to download.'):w.none):'';
  return {phase,noWinner,showWinner:finished&&job.restored===true,reportAvailable:finished||stopped};
}
export function profileLabel(profile,language='ru'){
  if(profile?.name!=='Собранная стратегия · повторная проверка')return profile?.name||'';
  const r=profile.components,plain=r&&['http','tls','quic'].every(k=>r[k]?.method==='pass')&&(!r.overrides||r.overrides.length===0);
  return language==='ru'?(plain?'Собранная стратегия · без методов обхода · повторная проверка':'Собранная стратегия · итоговая повторная проверка'):
    (plain?'Assembled strategy · no bypass methods · repeat verification':'Assembled strategy · final repeat verification');
}
export function retryHint(language='ru'){
  return language==='ru'?'Один прогон проверяет только часть вариантов. Можно заранее указать число прогонов — второй, третий и следующие начнутся автоматически после восстановления настроек. Генератор использует результаты предыдущих прогонов и исследует новые сочетания. Исходная стратегия, соединение без обхода и лучшие варианты проходят контрольные повторные замеры. Результат может стать лучше, но это не гарантируется. Каждый прогон завершается отдельно; применение найденной стратегии — ваш отдельный выбор.':'One run checks only part of the available variants. Choose the run count beforehand: a second, third or later run starts automatically after restoring settings. The generator uses previous results and explores new combinations. The original strategy, pass-through and leading candidates get control remeasurements. Results may improve, but improvement is not guaranteed. Each run finishes separately; applying a strategy remains your choice.';
}
export function goalLabel(goal='all',language='ru'){
  const names={youtube:'YouTube',discord:'Discord',instagram:'Instagram',torrents:language==='ru'?'Торрент-трекеры':'Torrent trackers'};
  return goal==='all'?(language==='ru'?'все сервисы':'all services'):goal.split(',').map(s=>names[s]||s).join(' + ');
}
export function selectionDescription(goal,search,language='ru',custom=null){
  if(custom){const scope=customScope(custom.hosts,custom.only,goal,language);return scope===null?null:
    (language==='ru'?'Разработка стратегии. ':'Strategy generation. ')+scope;}
  const scope=goalLabel(goal,language);
  const method=language==='ru'?(search==='synthesis'?'Разработать стратегию':'Сравнить готовые профили'):(search==='synthesis'?'Develop a strategy':'Compare existing profiles');
  return method+'. '+(language==='ru'?'Цель: ':'Goal: ')+scope+'.';
}
export function searchDescription(search,language='ru'){
  if(search!=='synthesis')return language==='ru'?'Сравниваются текущая, стандартная и подходящие стратегии из каталога вместе с их файлами. Новая стратегия с нуля в этом режиме не создаётся.':'Compare the current, stock and compatible signed-catalog profiles with their dependencies. This mode does not generate a strategy from scratch.';
  return language==='ru'?'Генератор стратегий проходит бета-тестирование. Он проверяет методы для HTTP, TLS и QUIC и уточняет поиск по результатам. Результаты прошлых запусков направляют поиск. В одной серии одинаковые поисковые сочетания исключаются; контрольные замеры исходной стратегии, соединения без обхода и лучших вариантов повторяются. Лучшие варианты проходят повторные замеры; улучшение не гарантируется. Каталог готовых стратегий не требуется. Проверки выполняются по IPv4.':'The strategy generator is in beta. It tests methods for HTTP, TLS and QUIC and refines the search using the results. Previous results guide the search. Identical exploratory combinations are excluded within a series; the original strategy, pass-through and leading candidates get repeated control measurements. Leading candidates are measured repeatedly; improvement is not guaranteed. No strategy catalog is required. Checks use IPv4.';
}
export function reportDescription(search,language='ru'){
  if(search!=='synthesis')return language==='ru'?'Для каждого профиля: предварительная проверка и обучение и два измерения. Показаны диапазоны успешных проверок. DNS проверяется отдельно и не влияет на рейтинг.':'Each profile gets the same AUTO warmup and two recorded runs. Successful-check ranges are shown. DNS is tested separately and does not affect ranking.';
  return language==='ru'?'Предварительные замеры помогают выбрать варианты для повторной проверки. Итог сравнивается с вашей исходной стратегией и соединением без обхода. Применение выполняется отдельно.':'Exploratory measurements select candidates for repeat checks. The result is compared with your original strategy and pass-through. Applying it is a separate step.';
}
export function generationSummary(generation,language='ru'){
  const fromZero=generation?.from_zero?.eligible===true;
  const versusCurrent=generation?.verified===true&&generation?.versus_current?.eligible===true;
  if(language==='ru')return fromZero?
    'Новая стратегия собрана без каталога. Рост по выбранной цели относительно пустой основы подтверждён повторными измерениями. '+
      (versusCurrent?'Подтверждено улучшение по выбранной цели относительно исходной стратегии.':'Ваша исходная стратегия сохранена: преимущества над ней не подтверждены.'):
    'Для собранного варианта рост относительно пустой основы пока не подтверждён. Это результат проверенной части матрицы, не всех возможных сочетаний.';
  return fromZero?
    'A new strategy was generated without the catalog. Repeated measurements confirmed improvement for the selected goal over pass-through. '+
      (versusCurrent?'It also improved the selected goal compared with the original strategy.':'The original was retained: improvement over it was not confirmed.'):
    'The assembled candidate did not confirm improvement over pass-through. Only the recorded part of the matrix was tested.';
}
export function ranges(runs,service=null){
  if(!Array.isArray(runs)||(runs.length!==1&&runs.length!==2))return [];
  const first=service?runs[0]?.services?.[service]:runs[0]?.metrics,last=runs[runs.length-1],second=service?last?.services?.[service]:last?.metrics;
  if(!first||!second)return [];
  const out=[];
  for(const key of (service?['http','tls12','tls13','quic']:['tcp','http','tls12','tls13','quic'])){
    const a=first[key],b=second[key];
    if(![a,b].every(v=>v&&Number.isSafeInteger(v.ok)&&Number.isSafeInteger(v.total)&&v.ok>=0&&v.total>=v.ok)||a.total!==b.total)return [];
    out.push({key,low:Math.min(a.ok,b.ok),high:Math.max(a.ok,b.ok),total:a.total});
  }
  return out;
}
function validProfileCollection(profiles){return Array.isArray(profiles)&&profiles.every(p=>p&&typeof p==='object'&&!Array.isArray(p));}
export function tradeoffComparison(job,candidate){
  const unknown={known:false,losses:[]};
  if(!validProfileCollection(job?.profiles))return unknown;
  const originals=Array.isArray(job?.profiles)?job.profiles.filter(p=>p?.rank?.reason==='baseline'):[];
  if(originals.length!==1||!Array.isArray(originals[0].runs)||originals[0].runs.length!==2||!Array.isArray(candidate?.runs)||candidate.runs.length!==2)return unknown;
  const original=originals[0],runs=[...original.runs,...candidate.runs];
  for(const key of ['targets','context_sha256']){
    const value=runs[0]?.[key];
    if(typeof value!=='string'||!/^[a-f0-9]{64}$/.test(value)||runs.some(r=>r?.[key]!==value))return unknown;
  }
  const before=ranges(original.runs),after=ranges(candidate.runs);
  if(before.length!==5||after.length!==5||before.some((v,i)=>v.total!==after[i].total))return unknown;
  return {known:true,losses:before.flatMap((v,i)=>after[i].low<v.low?[{key:v.key,baseline:v.low,candidate:after[i].low,total:v.total}]:[])};
}
export function tradeoffNotice(job,candidate,language='ru'){
  const v=tradeoffComparison(job,candidate);
  if(!v.known)return language==='ru'?'Общие проверки по этому отчёту сопоставить не удалось. Применение недоступно; сохраните отчёт и повторите подбор.':'General checks cannot be compared from this report. Apply is unavailable; save the report and repeat the search.';
  if(!v.losses.length)return '';
  const names={tcp:'TCP',http:'HTTP',tls12:'TLS 1.2',tls13:'TLS 1.3',quic:'QUIC'};
  const values=v.losses.map(m=>`${names[m.key]} ${m.baseline}/${m.total} → ${m.candidate}/${m.total}`).join('; ');
  return language==='ru'?`В повторных измерениях снизились общие показатели: ${values}. Показан худший результат из двух измерений.`:`General checks decreased in repeated measurements: ${values}. Values are the lower result from two runs.`;
}
function winnerProfile(job){
  const found=Array.isArray(job?.profiles)?job.profiles.filter(p=>p&&p.id+(p.recipe!==undefined?':'+p.recipe:'')===job.winner):[];
  const p=found?.length===1?found[0]:null;
  return p?.rank?.eligible===true&&!p.error&&p.sample_type!=='exploratory'?p:null;
}
export function applyDescription(job,language='ru',torrentSites=false){
  const p=winnerProfile(job);
  if(job?.state!=='completed'||job.restored!==true||job.can_apply!==true||!p||!tradeoffComparison(job,p).known)return null;
  const goal=Array.isArray(job.custom_hosts)?customScope(job.custom_hosts,job.custom_only,job.goal||'all',language):goalLabel(job.goal||'all',language),notice=tradeoffNotice(job,p,language);
  if(goal===null)return null;
  const base=language==='ru'?`Применить этот общий профиль целиком? Цель проверки: ${goal}. Состав правил изменится; исходные файлы будут сохранены. Проверки выполнялись по IPv4.`:`Apply this complete common profile? Measured goal: ${goal}. Its rules will replace the current strategy; original resource files are preserved. Measurements cover IPv4.`;
  const addon=torrentSites?(language==='ru'?' Дополнение для торрент-трекеров будет добавлено без отдельного измерения.':' The tracker extension is not separately measured.'):'';
  return base+(notice?' '+notice:'')+addon;
}
function recoveryBlocked(j){return j?.state==='recovery_required'&&j.can_restart!==true;}
const words={ru:{start:'Начать подбор',cancel:'Остановить и восстановить',refresh:'Обновить',apply:'Применить этот вариант',download:'Скачать отчёт JSON',baseline:'Исходная стратегия',eligible:'Подтверждённое улучшение по выбранной цели',no_improvement:'Улучшение не подтверждено',tls_regression:'Ухудшение TLS',youtube_regression:'Ухудшение проверок YouTube',incomparable_result:'Несопоставимые результаты',complete:'Подбор завершён',catalog:'Подготовка профилей',dns:'Проверка DNS',switching:'Переключение стратегии',warming:'Предварительная проверка и обучение',measuring_1:'Первое измерение',measuring_2:'Повторное измерение',restoring:'Восстановление исходного состояния',applying:'Применение выбранной стратегии',applied:'Стратегия применена',backup:'Резервная копия',restored:'Исходная конфигурация восстановлена.',notrestored:'Восстановление ещё не подтверждено.',none:'Подтверждённого улучшения не найдено — сохранена исходная стратегия.',best:'Рекомендуемый вариант: ',not_installed:'Сначала установите DPI Detector кнопкой в основной панели.',busy:'Устройство занято другой операцией. Дождитесь завершения.',insufficient_memory:'Недостаточно свободной памяти для безопасной проверки.',insufficient_space:'Недостаточно места для резервной копии и ресурсов.',source_changed:'Настройки изменены вне подбора. Чужие изменения не перезаписаны; требуется проверка.',recovery_required:'Восстановление не подтверждено. Скачайте отчёт; новый подбор заблокирован.',split_mode_active:'Для подбора сначала включите общий режим стратегий.',all_mode_not_supported:'Выберите режим «Авто» или «Список». Режим «Всё» в подборе не используется.',cancelled:'Остановлен пользователем.',timed_out:'Проверка не завершилась за отведённое время.',interrupted:'Проверка была прервана.',goal_no_improvement:'Улучшение выбранных сервисов не подтверждено',goal_regression:'Ухудшение выбранного сервиса',failed:'Подбор не завершён. Сохраните отчёт для диагностики.',invalid_synthesis_recipe:'Не удалось собрать вариант стратегии. Подбор остановлен. Сохраните отчёт.',unsupported_abi:'Для этой архитектуры нет совместимого DPI Detector; подбор недоступен.',unsupported_runtime:'Не удалось запустить проверку с выбранными параметрами. Уменьшите число запросов; если ошибка повторится, сохраните отчёт.',storage_unavailable:'Хранилище подбора недоступно. Сохраните имеющийся отчёт и проверьте накопитель.',detector_failed:'DPI Detector не завершил измерение. Сохраните отчёт.',service_start_failed:'Не удалось запустить службу. Сохраните отчёт.',service_stop_failed:'Не удалось остановить службу. Сохраните отчёт.',service_check_failed:'Не удалось подтвердить работу службы. Сохраните отчёт.',lua_trust:'Для Lua требуется явное доверие; профиль пропущен.',unresolved_profile_resource:'Недоступны необходимые списки, блобы или Lua.',choose_goal:'Выберите хотя бы один сервис.',stale_state:'Отчёт устарел. Выполните подбор повторно.',auth:'Войдите в основную панель и откройте подбор снова.'},en:{start:'Start selection',cancel:'Stop and restore',refresh:'Refresh',apply:'Apply this strategy',download:'Download JSON report',baseline:'Original strategy',eligible:'Confirmed improvement for the selected goal',no_improvement:'No confirmed improvement',tls_regression:'TLS regression',youtube_regression:'YouTube checks regressed',incomparable_result:'Incomparable results',complete:'Selection complete',catalog:'Preparing profiles',dns:'Checking DNS',switching:'Switching strategy',warming:'Equal AUTO warmup',measuring_1:'First measurement',measuring_2:'Repeat measurement',restoring:'Restoring original state',applying:'Applying strategy',applied:'Strategy applied',backup:'Backup',restored:'Original configuration restored.',notrestored:'Restoration has not been confirmed yet.',none:'No confirmed improvement; the original strategy was retained.',best:'Recommended strategy: ',not_installed:'Install DPI Detector from the main panel first.',busy:'Another operation is using the device.',insufficient_memory:'Not enough available memory.',insufficient_space:'Not enough storage for backup and resources.',source_changed:'Settings changed outside this operation; foreign changes were preserved.',recovery_required:'Restoration is not confirmed. Download the report; new selection is blocked.',split_mode_active:'Switch to common strategy mode first.',all_mode_not_supported:'Use AUTO or LIST mode; ALL is excluded.',cancelled:'Stopped by the user.',timed_out:'Time limit reached.',interrupted:'Interrupted.',goal_no_improvement:'No confirmed improvement for selected services',goal_regression:'A selected service regressed',failed:'Selection did not finish. Save the diagnostic report.',invalid_synthesis_recipe:'Could not build a strategy variant. Selection stopped. Save the report.',unsupported_abi:'No compatible DPI Detector is available for this architecture.',unsupported_runtime:'The checks could not start with these settings. Reduce the request count; if this recurs, share the report with Frank.',storage_unavailable:'Selection storage is unavailable. Save the report and check storage.',detector_failed:'DPI Detector did not finish the measurement. Save the report.',service_start_failed:'The service could not start. Save the report.',service_stop_failed:'The service could not stop. Save the report.',service_check_failed:'Service operation could not be confirmed. Save the report.',lua_trust:'Lua requires explicit trust; profile skipped.',unresolved_profile_resource:'Required lists, blobs or Lua are unavailable.',choose_goal:'Select at least one service.',stale_state:'This report is outdated. Run selection again.',auth:'Sign in to the main panel, then reopen this page.'}};
Object.assign(words.ru,{synthesis_setup:'Подготовка подбора',discovering:'Проверка методов и параметров',assembling:'Сборка правил по результатам',zero_baseline:'Стратегия временно отключена, чтобы сравнить обычное соединение с работой обхода. После проверки подбор продолжится.',exploratory:'Предварительный результат · нужна повторная проверка',synthesis_lua_unavailable:'Стандартные Lua не совпадают с проверенной версией пакета. Генерация не начата.',synthesis_unverified:'Для этой стратегии нет подтверждённой повторной проверки.',retested:'Вариант проверен повторно',protocol_regression:'Часть ранее успешных проверок перестала проходить',export:'Скачать стратегию с нужными файлами'});
Object.assign(words.en,{synthesis_setup:'Preparing strategy generation',discovering:'Testing methods and parameters',assembling:'Assembling measured rules',zero_baseline:'Pass-through control',exploratory:'One exploratory sample · not a recommendation',synthesis_lua_unavailable:'Standard Lua does not match the verified package. Generation has not started.',synthesis_unverified:'This strategy has no confirmed repeat validation.',retested:'Retested candidate',protocol_regression:'Some previously successful checks stopped passing',export:'Download strategy with required files'});
Object.assign(words.ru,{invalid_custom_targets:'Проверьте список своих сайтов.',request_conflict:'Этот запрос уже связан с другим набором целей. Обновите отчёт и начните новый подбор.',selection_changed:'Выбор изменился. Проверьте его и начните снова.',custom_regression:'Ухудшение проверки своего сайта',native_regression:'Ухудшение встроенных контрольных проверок',custom_budget_unavailable:'Не удалось подготовить все проверки. Измените список сайтов и повторите подбор.',synthesis_rule_limit:'Не удалось собрать все цели в допустимое число правил. Неполный вариант не предлагается.'});
Object.assign(words.en,{invalid_custom_targets:'Check the custom site list.',request_conflict:'This request already identifies different goals. Refresh the report and start a new search.',selection_changed:'Your selection changed. Review it and start again.',custom_regression:'A custom site check regressed',native_regression:'Built-in control checks regressed',custom_budget_unavailable:'A safe time budget is unavailable for these checks.',synthesis_rule_limit:'The complete target set exceeds the rule limit. No partial strategy is offered.'});
Object.assign(words.ru,{request_unconfirmed:'Ответ не получен. Работа на роутере может продолжаться. Обновите статус или повторите тот же запрос.',retry_request:'Повторить тот же запрос'});
Object.assign(words.en,{request_unconfirmed:'No response was received. Work on the router may continue. Refresh status or retry the same request.',retry_request:'Retry the same request'});
Object.assign(words.ru,{invalid_pool:'Введите целое число от 1 до 1000000 без пробелов и ведущих нулей.',concurrency_budget_unavailable:'Не удалось подготовить проверки с этим числом запросов. Уменьшите его и повторите.',plan_changed:'Условия проверки изменились. Выберите параметры и подтвердите новый план.'});
Object.assign(words.en,{invalid_pool:'Enter an integer from 1 to 1000000 without spaces or leading zeros.',concurrency_budget_unavailable:'This request pool cannot cover every target within the safe time limit.',plan_changed:'The test conditions changed. Review the selection and confirm a new plan.'});
words.ru.invalid_rounds='Введите целое число прогонов от 2 до 10.';words.en.invalid_rounds='Enter a whole number of runs from 2 to 10.';
Object.assign(words.ru,{
  measurement_saved:'Замеры сохранены. Сравнение с исходной ещё не подтверждено.',
  measurement_loading:'Загрузка замеров…',
  measurement_unavailable:'Не удалось открыть этот замер. Обновите отчёт и выберите его снова.',
});
Object.assign(words.en,{
  measurement_saved:'Measurements saved. The comparison with the original is unconfirmed.',
  measurement_loading:'Loading measurements…',
  measurement_unavailable:'This measurement could not be opened. Refresh the report and select it again.',
});
words.ru.auth='Сессия закончилась. Войдите в основную панель и обновите страницу.';words.en.auth='Your session expired. Sign in on the main panel and reload this page.';
export function remainingTime(job,active,since=0,language='ru'){
  if(!active||!Number.isFinite(job?.elapsed_seconds)||job.elapsed_seconds<0||!Number.isFinite(since)||since<0)return '';
  const progress=job.progress;
  if(!Number.isFinite(progress)||progress<=0||progress>=100)return language==='ru'?
    'Оценка времени до конца подбора появится после первых проверок.':
    'The time-to-completion estimate will appear after the first checks.';
  const estimate=Math.max(0,job.elapsed_seconds*(100-progress)/progress-since);
  const minutes=Math.max(1,Math.ceil(estimate/60));
  return language==='ru'?`Примерно до конца подбора: ${minutes} мин. Оценка уточняется по результатам проверок.`:
    `About ${minutes} min until the search finishes. The estimate updates as checks complete.`;
}
if(typeof document!=='undefined'){
  let csrf='',data=null,busy=false,language='ru',actionError='',pending=null,goalLoaded=false,customLoaded=false,customErrors=[],pageActive=true;const $=id=>document.getElementById(id);const t=key=>words[language][key]||key;
  let poolLoaded=false,roundsLoaded=false,draftPlan=null,timingJob=null,timingReceived=0;$('pool-value').value='100';$('rounds-value').value='2';
  let measuredJob=null,measuredOptions='',measuredView=null,measuredRequest=0,measuredStatus='';
  const requestedPool=()=>{const v=$('pool-value').value;return v==='auto'?null:poolChoice(v);};
  function text(id,value){$(id).textContent=value;}
  const metrics=new MetricsHistory();let metricsEpoch=0;
  function renderMetrics(){const v=metrics.view(performance.now(),language);for(const key of ['cpu','memory','temperature','freshness'])text('metric-'+key,v[key]);$('live-metrics').classList.toggle('stale',v.stale);const j=data?.job;if(j!==timingJob){timingJob=j;timingReceived=performance.now();}text('remaining',remainingTime(j,data?.active,(performance.now()-timingReceived)/1000,language));}
  async function call(cmd,extra={}){
    const p=new URLSearchParams({cmd,...(cmd==='status'?{}:{csrf_token:csrf}),...extra});
    const controller=new AbortController();
    const timeout=controller?setTimeout(()=>controller.abort(),15000):null;
    try{
    const r=await fetch('/index.php',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:p,...(controller?{signal:controller.signal}:{})});
    if(r.status===401||r.status===403){authenticated=false;pending=null;$('confirmation').hidden=true;if(data)data={...data,error:'auth'};poller.stop();render();throw new Error('auth');}
    const v=await r.json();if(!r.ok||v.error){const error=new Error(v.error||'failed');error.confirmed=true;throw error;}return v;
    }finally{if(timeout!==null)clearTimeout(timeout);}
  }
  let supplementStatusCurrent=false;
  const supplement=mountSupplement({document,request:call,language:()=>language,context:()=>({job:data?.job,
    available:pageActive&&authenticated&&supplementStatusCurrent&&!busy&&!pending&&!outstanding&&!data?.active&&!data?.error})});
  const mutationKey='nfqws-picker-pending-v1';
  function validMutation(v){
    if(!v||!['pickerstart','pickerextended','pickersynthesize','pickerapply','pickercancel'].includes(v.cmd)||!v.extra||typeof v.extra!=='object')return false;
    const e=v.extra;let keys=Object.keys(e).sort().join(',');
    if(['pickerapply','pickercancel'].includes(v.cmd))return /^[a-f0-9]{32}$/.test(e.id||'')&&
      (v.cmd==='pickercancel'?keys==='id':keys==='id,torrent_sites'&&['0','1'].includes(e.torrent_sites));
    if('concurrency'in e&&poolChoice(e.concurrency)===null||'plan_sha256'in e&&
      (typeof e.plan_sha256!=='string'||!/^[a-f0-9]{64}$/.test(e.plan_sha256)))return false;
    if('rounds'in e&&(v.cmd!=='pickersynthesize'||roundChoice(e.rounds)===null))return false;
    keys=Object.keys(e).filter(k=>!['concurrency','plan_sha256','rounds'].includes(k)).sort().join(',');
    if(!/^[a-f0-9]{32}$/.test(e.request_id||'')||e.consent!=='test'||typeof e.goal!=='string'||
      !(e.goal==='all'||e.goal.split(',').every(s=>['youtube','discord','instagram','torrents'].includes(s))))return false;
    if(keys==='consent,goal,request_id')return true;
    return v.cmd==='pickersynthesize'&&keys==='consent,custom_only,custom_sites,goal,request_id'&&
      typeof e.custom_sites==='string'&&['0','1'].includes(e.custom_only)&&customScope(e.custom_sites.split('\n'),e.custom_only==='1',e.goal,'en')!==null;
  }
  let outstanding=null;try{const saved=JSON.parse(sessionStorage.getItem(mutationKey));if(validMutation(saved))outstanding=saved;}catch{}
  function rememberMutation(value){outstanding=value;try{if(value)sessionStorage.setItem(mutationKey,JSON.stringify(value));else sessionStorage.removeItem(mutationKey);}catch{}}
  function reconcile(result){
    if(!outstanding)return;
    const {cmd,extra}=outstanding,j=result?.job;
    if((extra.request_id&&j?.request_id===extra.request_id)||j?.id===extra.id&&
      (cmd==='pickercancel'&&!result.active||cmd==='pickerapply'&&['applying','applied','failed','cancelled','interrupted','recovery_required'].includes(j.state))){
      rememberMutation(null);if(actionError==='request_unconfirmed')actionError='';
    }
  }
  let torrentJob=null;
  function draftKey(){return JSON.stringify([language,$('search').value,$('extended').checked,$('goal-all').checked,
    ...['youtube','discord','instagram','torrents'].map(s=>$('goal-'+s).checked),$('custom-enabled').checked,$('custom-only').checked,$('custom-sites').value,$('pool-value').value,$('rounds-value').value]);}
  function pendingStartCurrent(p){return pageActive&&!data?.active&&!data?.error&&data?.detector?.installed===true&&
    !recoveryBlocked(data?.job)&&p.snapshot===draftKey()&&(!p.extra.custom_sites||data?.custom_capability?.available===true);}
  function pendingApplyCurrent(p){
    return !data?.active&&!data?.error&&data?.job?.id===p.extra.id&&data.job.winner===p.winner&&
      (p.extra.torrent_sites!=='1'||data.job.can_add_torrent_sites===true)&&
      p.message===applyDescription(data.job,language,p.extra.torrent_sites==='1');
  }
  const columnPreferenceKey='nfqws2-result-columns';
  const columnPicker=$('result-columns');
  const resultGrid=$('results');
  function showResultColumnCount(){
    const layout=window.getComputedStyle?.(resultGrid);
    if(!layout)return;
    const fitted=layout.gridTemplateColumns.split(' ').length;
    const requested=columnPicker.value;
    text('result-column-count',requested!=='auto'&&fitted<Number(requested)?
      (language==='ru'?`Вмещается ${fitted} из ${requested}`:`${fitted} of ${requested} columns fit`):'');
  }
  function setResultColumns(value){
    const mode=/^(?:auto|[1-6])$/.test(value)?value:'auto';
    columnPicker.value=mode;
    resultGrid.className='result-columns-'+mode;
    showResultColumnCount();
  }
  try{setResultColumns(localStorage.getItem(columnPreferenceKey));}catch{setResultColumns('auto');}
  columnPicker.addEventListener('change',()=>{
    setResultColumns(columnPicker.value);
    try{localStorage.setItem(columnPreferenceKey,columnPicker.value);}catch{}
  });
  if(typeof ResizeObserver==='function')new ResizeObserver(showResultColumnCount).observe($('results-section'));
  function renderProfile(profile,job,fallback){
    const row=document.createElement('article');
    row.className='result'+(profile.name==='Собранная стратегия · повторная проверка'?' assembled-final':'');
    const title=document.createElement('h3');
    if(profile.name==='Собранная стратегия · повторная проверка'){
      const label=document.createElement('strong');
      label.textContent=profileLabel(profile,language);
      title.append(label);
    }else title.textContent=profileLabel(profile,language);
    row.append(title);
    const ru=language==='ru';
    const protocolLabels={tcp:'TCP',http:'HTTP',tls12:'TLS 1.2',tls13:'TLS 1.3',quic:'QUIC'};
    const table=document.createElement('table');
    table.className='result-table';
    const head=document.createElement('thead'),header=document.createElement('tr');
    for(const label of [ru?'Сервис':'Service',protocolLabels.http,protocolLabels.tls12,protocolLabels.tls13,protocolLabels.quic]){
      const cell=document.createElement('th');
      cell.scope='col';cell.textContent=label;header.append(cell);
    }
    head.append(header);
    const body=document.createElement('tbody');
    const services=!job.goal||job.goal==='all'?['youtube','discord','instagram','torrents']:job.goal.split(',');
    for(const service of services){
      const measured=ranges(profile.runs,service);
      const serviceRow=document.createElement('tr'),name=document.createElement('th');
      name.scope='row';
      name.textContent={youtube:'YouTube',discord:'Discord',instagram:'Instagram',torrents:ru?'Торрент-трекеры':'Torrent trackers'}[service]||service;
      serviceRow.append(name);
      if(measured.length){
        for(const range of measured){
          const cell=document.createElement('td');
          cell.textContent=formatRatio(range);serviceRow.append(cell);
        }
      }else{
        const cell=document.createElement('td');
        cell.colSpan=4;cell.textContent=ru?'Нет замеров':'Not measured';serviceRow.append(cell);
      }
      body.append(serviceRow);
    }
    const foot=document.createElement('tfoot'),totalsRow=document.createElement('tr'),totalsCell=document.createElement('td');
    totalsCell.colSpan=5;
    const totalsTitle=document.createElement('span');
    totalsTitle.className='totals-title';totalsTitle.textContent=ru?'Все сайты':'All sites';
    const metrics=document.createElement('div');
    metrics.className='metrics';
    for(const range of ranges(profile.runs)){
      const value=document.createElement('span');
      value.textContent=protocolLabels[range.key]+': '+formatRatio(range);
      metrics.append(value);
    }
    if(!metrics.childNodes.length)metrics.textContent=language==='ru'?'Показатели недоступны':'Metrics unavailable';
    totalsCell.append(totalsTitle);totalsCell.append(metrics);totalsRow.append(totalsCell);foot.append(totalsRow);
    table.append(head);table.append(body);table.append(foot);row.append(table);
    if(Array.isArray(job.custom_hosts)){
      const v=customMeasurements(profile.custom_runs),label=document.createElement('p');
      label.className='custom-metrics';
      label.textContent=v?(language==='ru'?`Свои сайты · ${v.repeats===2?'успешно в обоих замерах':'предварительный замер'}: ${v.stable}/${v.total}. Ответ транспорта: ${v.responded}/${v.total}.`:
        `Custom sites · ${v.repeats===2?'successful in both runs':'exploratory sample'}: ${v.stable}/${v.total}. Transport responses: ${v.responded}/${v.total}.`):t('incomparable_result');
      row.append(label);
      for(const site of v?.rows||[]){
        const line=document.createElement('p'),ratio=c=>`${c.low===c.high?c.low:c.low+'–'+c.high}/1`;
        line.className='custom-metrics';
        line.textContent=`${site.host}: TLS 1.2 ${ratio(site.tls12)} · TLS 1.3 ${ratio(site.tls13)}`;
        row.append(line);
      }
    }
    const why=document.createElement('p');
    why.textContent=t(profile.error||(profile.rank?.eligible?'eligible':profile.rank?.reason)||fallback);
    row.append(why);
    return row;
  }
  function formatRatio({low,high,total}){
    return `${low===high?low:`${low}–${high}`}/${total}`;
  }
  function renderMeasured(job){
    const picker=$('measured-select'),detail=$('measured-detail'),ru=language==='ru';
    const items=jobView(job,language).reportAvailable&&Array.isArray(job?.measured_results)?
      job.measured_results.filter(item=>item&&typeof item.id==='string'&&item.id.length===32&&
        /^[a-f0-9]{32}$/.test(item.id)&&Number.isInteger(item.round)&&Number.isInteger(item.number)&&typeof item.name==='string'):[];
    if(job?.id!==measuredJob){
      measuredJob=job?.id;measuredView=null;measuredStatus='';measuredRequest++;picker.value='';
    }
    const value=picker.value;
    const signature=JSON.stringify([language,items]);
    if(signature!==measuredOptions){
      measuredOptions=signature;
      const prompt=document.createElement('option');prompt.value='';
      prompt.textContent=ru?'Выберите замер':'Choose a measurement';
      picker.replaceChildren(prompt);
      for(const item of items){
        const option=document.createElement('option');option.value=item.id;
        option.textContent=ru?`Прогон ${item.round} · ${item.number}. ${item.name}`:
          `Run ${item.round} · ${item.number}. ${profileLabel(item,language)}`;
        picker.append(option);
      }
      picker.value=items.some(item=>item.id===value)?value:'';
    }
    const entry=items.find(item=>item.id===picker.value);
    const selected=entry&&measuredView?.id===entry.id?measuredView:null;
    const canUse=Boolean(selected?.can_export&&entry.document_available&&job.restored===true&&
      !data.active&&!data.error&&!pending&&!outstanding&&pageActive&&authenticated);
    $('measured-section').hidden=!items.length;
    picker.disabled=!authenticated||busy;
    text('measured-title',ru?'Замеры по прогонам':'Measurements by run');
    text('measured-label',ru?'Вариант из серии':'Result from the series');
    text('measured-report',ru?'Скачать замеры JSON':'Download measurements as JSON');
    text('measured-export',ru?'Скачать стратегию JSON':'Download strategy as JSON');
    text('measured-import',ru?'Открыть в импорте':'Open in Import');
    text('measured-status',measuredStatus?t(measuredStatus):
      selected&&!entry.document_available?(ru?'Для этого варианта доступны только замеры.':'Only measurements are available for this result.'):'');
    detail.replaceChildren();
    if(selected)detail.append(renderProfile(selected.profile,job,
      selected.profile.sample_type==='exploratory'?'exploratory':'measurement_saved'));
    $('measured-report').hidden=!selected;
    $('measured-report').disabled=busy||!authenticated;
    for(const id of ['measured-export','measured-import']){
      $(id).hidden=!canUse;
      $(id).disabled=busy||!canUse;
    }
  }
  function render(){
    supplement.render();
    // Clear actionable output before inspecting a refreshed report. A malformed
    // response must never leave the previous recommendation or approval visible.
    $('apply').hidden=true;for(const id of ['winner','tradeoffs','generation','matrix','measured-goal','explanation','custom-summary'])text(id,'');$('tradeoffs').hidden=true;$('custom-summary').hidden=true;
    if(pending?.cmd==='pickerapply'&&!pendingApplyCurrent(pending)){pending=null;$('confirmation').hidden=true;actionError='stale_state';}
    if(pending&&pending.cmd!=='pickerapply'&&!pendingStartCurrent(pending)){pending=null;$('confirmation').hidden=true;actionError='selection_changed';}
    renderMetrics();
    if(!data)return;const j=data.job,active=data.active,locked=active||recoveryBlocked(j),view=j?jobView(j,language):null;
    if(!poolLoaded||active||recoveryBlocked(j)){
      const e=outstanding?.extra,c=!active&&e?.request_id?{requested:e.concurrency||'auto',effective:e.concurrency?Number(e.concurrency):data.budget?.concurrency}:recordedPool(j);
      $('pool-value').value=c&&c.requested!=='auto'?c.requested:locked&&c?String(c.effective):'100';poolLoaded=true;
    }
    if(!roundsLoaded||locked){$('rounds-value').value=String(locked?(j?.rounds||1):(outstanding?(outstanding.extra.rounds||1):2));roundsLoaded=true;}
    const requested=requestedPool(),planned=draftPlan?.snapshot===draftKey()?draftPlan.plan:null;
    const b=locked?j.budget:planned?.budget||data.budget;
    const shownChoice=active||recoveryBlocked(j)?recordedPool(j):planned?.concurrency_choice||
      (requested===null?null:{requested,effective:requested==='auto'?data.budget?.concurrency:Number(requested)});
    text('pool-selected',poolDescription(shownChoice,language)||t('incomparable_result'));
    text('pool-error',requested===null?t('invalid_pool'):'');$('pool-controls').hidden=false;
    $('pool-fieldset').disabled=busy||active||recoveryBlocked(j)||Boolean(data.error)||Boolean(pending)||Boolean(outstanding);
    text('device',b?(language==='ru'?`Ядер процессора: ${b.cores}. Свободная память${data.active?' при запуске':''}: ${Math.round(b.available_kib/1024)} МиБ`:`CPU cores: ${b.cores}. Available memory${data.active?' at start':''}: ${Math.round(b.available_kib/1024)} MiB`):t(data.error||'failed'));
    text('limits',b?(language==='ru'?`Пул запросов: до ${b.concurrency}. Будут сравнены сохранённые стратегии и до 3 дополнительных вариантов.`:`Request pool: up to ${b.concurrency}. Saved strategies and up to 3 additional variants will be compared.`):'');
    const validProfiles=validProfileCollection(j?.profiles);
    const profiles=validProfiles?j.profiles:[];
    if(locked)$('search').value=j.search==='synthesis'?'synthesis':'profiles';
    const synthesis=$('search').value==='synthesis';$('search').disabled=busy||locked||Boolean(pending)||Boolean(outstanding);
    $('rounds-fieldset').hidden=!synthesis;$('rounds-fieldset').disabled=busy||locked||Boolean(pending)||Boolean(outstanding);
    const count=synthesis?roundChoice($('rounds-value').value):1,invalidCount=count===null||synthesis&&!locked&&!outstanding&&count<2;text('rounds-error',invalidCount?t('invalid_rounds'):'');
    if(!customLoaded||locked){$('custom-enabled').checked=Array.isArray(j?.custom_hosts)&&j.custom_hosts.length>0;
      $('custom-sites').value=Array.isArray(j?.custom_hosts)?j.custom_hosts.join('\n'):'';$('custom-only').checked=j?.custom_only===true;$('custom-joint').checked=!$('custom-only').checked;customLoaded=true;}
    const custom=synthesis&&$('custom-enabled').checked,customOnly=custom&&$('custom-only').checked;
    $('custom-fieldset').hidden=!synthesis;$('custom-fieldset').disabled=busy||locked||Boolean(pending)||Boolean(outstanding);$('custom-settings').hidden=!custom;
    text('custom-errors',targetErrors(customErrors,language));
    const customBudget=locked?j?.budget:planned?.budget||data.custom_capability?.budget;
    text('custom-budget',custom?(data.custom_capability?.available===true||locked?
      (language==='ru'?`Свои сайты будут проверены вместе со встроенными. После завершения или остановки вернутся исходные настройки.`:`Custom sites are checked alongside built-in sites. Original settings are restored after completion or cancellation.`):t(data.custom_capability?.code||'unsupported_runtime')):'');
    text('search-help',searchDescription($('search').value,language));
    $('extended-control').hidden=synthesis;$('extended-help').hidden=synthesis;
    if(synthesis&&b){const g=locked?(j.matrix||data.generator):data.generator,shown=custom&&customBudget?customBudget:b;text('limits',language==='ru'?`Пул запросов: до ${shown.concurrency}. Будут проверены до ${g?.max_trials||8} вариантов, затем собранная стратегия проверяется повторно.`:`Request pool: up to ${shown.concurrency}. Up to ${g?.max_trials||8} variants will be tested, followed by repeated checks of the assembled strategy.`);}
    if(!locked&&requested!=='auto'&&!planned){
      const message=requested===null?t('invalid_pool'):(language==='ru'?`Выбрано вручную: пул до ${requested} параллельных запросов.`:`Selected manually: a pool of up to ${requested} parallel requests.`);
      text('limits',message);if(custom)text('custom-budget',message);
    }
    if(j?.id!==torrentJob){$('torrent-sites').checked=false;torrentJob=j?.id;}
    $('torrent-control').hidden=!j?.can_export;
    $('torrent-sites').disabled=busy||active||Boolean(pending)||Boolean(outstanding)||!j?.can_add_torrent_sites;
    if(!j?.can_add_torrent_sites)$('torrent-sites').checked=false;
    $('export').hidden=!j?.can_export||Boolean(data.error);$('export').disabled=busy||active||Boolean(pending)||Boolean(outstanding);
    if(!goalLoaded||locked){$('extended').checked=Boolean(j?.extended);const goal=j?.goal||'all';$('goal-all').checked=goal==='all';$('goal-selected').checked=goal!=='all';for(const service of ['youtube','discord','instagram','torrents'])$('goal-'+service).checked=goal==='all'||goal.split(',').includes(service);goalLoaded=true;}
    $('goals').disabled=busy||locked||Boolean(pending)||Boolean(outstanding)||customOnly;
    for(const service of ['youtube','discord','instagram','torrents']){if($('goal-all').checked)$('goal-'+service).checked=true;$('goal-'+service).disabled=$('goal-all').checked||customOnly;}
    $('start').disabled=busy||active||Boolean(pending)||Boolean(outstanding&&!outstanding.extra.request_id)||!data.detector.installed||Boolean(data.error)||recoveryBlocked(j)||requested===null||invalidCount||custom&&data.custom_capability?.available!==true;
    $('cancel').hidden=!active;$('cancel').disabled=busy||Boolean(data.error)||Boolean(outstanding&&outstanding.extra.id!==j?.id);$('extended').disabled=locked||busy||Boolean(pending)||Boolean(outstanding);
    $('progress-section').hidden=!j;$('results-section').hidden=!j||(validProfiles&&!profiles.length);
    for(const id of ['start','cancel','refresh','apply','download','export'])text(id,t(id));if(outstanding?.extra.request_id)text('start',t('retry_request'));
    text('error',actionError?t(actionError):(j?.code?t(j.code):(data.error?t(data.error):(!data.detector.installed?t(data.detector.code||'not_installed'):''))));
    $('download').hidden=data.active===true||!view?.reportAvailable;
    $('share-report').hidden=$('download').hidden;$('share-report').disabled=busy;
    $('share-export').hidden=$('export').hidden;$('share-export').disabled=$('export').disabled;
    text('repeat-hint',retryHint(language));
    const series=j?.series;text('series-status',series?(language==='ru'?
      `${active?'Серия выполняется':'Серия завершена или остановлена'}: прогон ${series.current} из ${series.total}. Завершено: ${series.completed}.${series.selected?` В отчёте — результат прогона ${series.selected}.`:''}`:
      `${active?'Series running':'Series finished or stopped'}: run ${series.current} of ${series.total}. Completed: ${series.completed}.${series.selected?` The report shows the result from run ${series.selected}.`:''}`):'');
    renderMeasured(j);
    if(!j)return;
    text('phase',view.phase);text('current',profileLabel(profiles.find(p=>p.name===j.current_name)||{name:j.current_name},language));$('progress').value=j.progress||0;
    text('restore',j.state==='applied'?t('applied'):t(j.restored?'restored':'notrestored'));
    if(!validProfiles){$('results').replaceChildren();text('error',t('incomparable_result'));text('tradeoffs',tradeoffNotice(j,null,language));$('tradeoffs').hidden=false;return;}
    text('torrent-applied-note',addonNotice(j,language));
    text('measured-goal',(language==='ru'?(j.search==='synthesis'?'Отчёт генератора · цель: ':'Отчёт сравнения готовых профилей · цель: '):(j.search==='synthesis'?'Generation report · goal: ':'Existing-profile comparison · goal: '))+((j.goal||'all')==='all'?(language==='ru'?'все сервисы':'all services'):j.goal.split(',').map(s=>({youtube:'YouTube',discord:'Discord',instagram:'Instagram',torrents:language==='ru'?'Торрент-трекеры':'Torrent trackers'}[s]||s)).join(' + ')));
    text('explanation',reportDescription(j.search,language));
    if(Array.isArray(j.custom_hosts))text('measured-goal',(language==='ru'?'Отчёт генератора · ':'Generation report · ')+(customScope(j.custom_hosts,j.custom_only,j.goal||'all',language)||t('incomparable_result')));
    const comparison=customComparison(j);if(comparison){$('custom-summary').hidden=false;text('custom-summary',language==='ru'?
      `Свои сайты · до: ${comparison.before}/${comparison.total} → после: ${comparison.after}/${comparison.total}. Успешный HTTPS-ответ подтверждён в обоих замерах, отдельно для TLS 1.2 и 1.3.`:
      `Custom sites · before: ${comparison.before}/${comparison.total} → after: ${comparison.after}/${comparison.total}. Root HTTPS success in both runs, separately for TLS 1.2 and 1.3.`);}
    text('matrix',j.matrix?(language==='ru'?`Матрица ${j.matrix.knowledge_version}: проверено ${j.matrix.tested}/${j.matrix.max_trials} опытов.${j.matrix.space_kind==='factorized_grid'?` Схема общих параметров: ${j.matrix.space_size} сочетаний до фильтрации; доменные правила сюда не входят.`:''}${j.matrix.stopped_by_budget?' Поиск ограничен бюджетом; матрица не исчерпана.':''}`:`Matrix ${j.matrix.knowledge_version}: ${j.matrix.tested}/${j.matrix.max_trials} trials.${j.matrix.space_kind==='factorized_grid'?` Shared parameter grid: ${j.matrix.space_size} combinations before filtering, excluding domain overrides.`:''}${j.matrix.stopped_by_budget?' Budget reached; the matrix was not exhausted.':''}`):'');
    text('generation',j.generation&&view.showWinner?generationSummary(j.generation,language):'');
    const result=$('results');result.replaceChildren();
    for(const p of profiles)result.append(renderProfile(p,j,'failed'));
    const winner=view.showWinner?winnerProfile(j):null;
    const winnerGoal=Array.isArray(j.custom_hosts)?(j.custom_only?(language==='ru'?'свои сайты':'custom sites'):goalLabel(j.goal||'all',language)+(language==='ru'?' + свои сайты':' + custom sites')):goalLabel(j.goal||'all',language);
    text('winner',winner?(language==='ru'?'Вариант по цели «':'Strategy for goal “')+winnerGoal+(language==='ru'?'»: ':'”: ')+winner.name+(j.state==='completed'&&!j.can_apply?' · '+t('stale_state'):''):view.noWinner);
    const notice=winner?tradeoffNotice(j,winner,language):'';text('tradeoffs',notice);$('tradeoffs').hidden=!notice;
    $('apply').hidden=active||Boolean(data.error)||!winner||applyDescription(j,language)===null;$('apply').disabled=busy||Boolean(outstanding&&outstanding.cmd!=='pickerapply');
    $('skipped').replaceChildren();for(const row of (Array.isArray(j.skipped)?j.skipped:[])){if(!row)continue;const li=document.createElement('li');li.textContent=row.id+': '+t(row.code);$('skipped').append(li);}
  }
  async function refresh(){if(busy)return;const epoch=metricsEpoch;try{
    const result=await metrics.request(()=>call('pickerstatus'),()=>epoch===metricsEpoch&&!document.hidden);if(result===null)return;
    supplementStatusCurrent=true;data=result;reconcile(result);
    const p=pending;
    if(p&&p.cmd!=='pickerapply'&&!pendingStartCurrent(p)){pending=null;$('confirmation').hidden=true;draftPlan=null;actionError='selection_changed';}
    else if(p&&p.cmd!=='pickerapply'&&p.planPost){
      const plan=await call('pickerplan',p.planPost);
      if(pending===p&&(!validPoolPlan(plan,p.selection)||plan.plan_sha256!==p.extra.plan_sha256)){
        pending=null;$('confirmation').hidden=true;draftPlan=null;actionError='plan_changed';
      }
    }
    render();
  }catch(e){supplementStatusCurrent=false;supplement.invalidate();if(pending&&pending.cmd!=='pickerapply'){pending=null;$('confirmation').hidden=true;draftPlan=null;}
    text('error',e.name==='AbortError'?(language==='ru'?'Статус не получен вовремя. Работа на роутере может продолжаться; повторите обновление.':'Status request timed out. Work on the router may continue; refresh again.'):t(e.message));}}
  const poller=new PickerStatusPoller(document,refresh,renderMetrics,()=>{metricsEpoch++;metrics.pause();});
  async function action(cmd,extra){
    metricsEpoch++;busy=true;actionError='';rememberMutation({cmd,extra:{...extra}});render();
    try{data=await call(cmd,extra);rememberMutation(null);}
    catch(e){
      if(e.confirmed){rememberMutation(null);actionError=e.message;}
      else{
        actionError=e.message==='auth'?'auth':'request_unconfirmed';
        if(authenticated)try{data=await call('pickerstatus');reconcile(data);}catch{/* Keep the exact canonical request for an explicit retry. */}
      }
    }finally{busy=false;render();}
  }
  function ask(cmd,extra,message){pending={cmd,extra,message,winner:data?.job?.winner,snapshot:draftKey(),
    planPost:extra.plan_sha256&&draftPlan?.snapshot===draftKey()?draftPlan.post:null,selection:draftPlan?.plan?.selection};text('confirmation-text',message);$('confirmation').hidden=false;render();}
  $('confirm-submit').addEventListener('click',()=>{const p=pending,valid=p&&(p.cmd==='pickerapply'?pendingApplyCurrent(p):pendingStartCurrent(p));pending=null;$('confirmation').hidden=true;if(!valid){actionError='stale_state';render();return;}void action(p.cmd,p.extra);});
  $('confirm-dismiss').addEventListener('click',()=>{pending=null;$('confirmation').hidden=true;render();});
  function draftChanged(){draftPlan=null;customErrors=[];if(['choose_goal','invalid_custom_targets','selection_changed','invalid_pool','plan_changed'].includes(actionError))actionError='';render();}
  for(const id of ['goal-all','goal-selected','goal-youtube','goal-discord','goal-instagram','goal-torrents','search','custom-enabled','custom-only','custom-joint'])$(id).addEventListener('change',draftChanged);
  $('custom-sites').addEventListener('input',draftChanged);
  $('pool-value').addEventListener('input',draftChanged);
  $('rounds-value').addEventListener('input',draftChanged);
  $('start').addEventListener('click',async()=>{
    if(busy||data?.active||data?.error||!data?.detector?.installed||recoveryBlocked(data?.job))return;
    if(outstanding){
      if(!outstanding.extra.request_id)return;
      const e=outstanding.extra,c=e.custom_sites?{hosts:e.custom_sites.split('\n'),only:e.custom_only==='1'}:null;
      const description=poolDescription({requested:e.concurrency||'auto',effective:e.concurrency?Number(e.concurrency):data?.budget?.concurrency},language)||'';
      ask(outstanding.cmd,{...e},selectionDescription(e.goal,outstanding.cmd==='pickersynthesize'?'synthesis':'profiles',language,c)+' '+description+' '+(language==='ru'?`Прогонов подряд: ${e.rounds||1}. `:`Sequential runs: ${e.rounds||1}. `)+t('request_unconfirmed'));return;
    }
    const custom=$('search').value==='synthesis' &&$('custom-enabled').checked,only=custom&&$('custom-only').checked;
    const goal=only||$('goal-all').checked?'all':['youtube','discord','instagram','torrents'].filter(s=>$('goal-'+s).checked).join(',');
    if(!goal){actionError='choose_goal';render();return;}
    const requested=requestedPool();if(requested===null){actionError='invalid_pool';render();return;}
    const rounds=$('search').value==='synthesis'?$('rounds-value').value:'1';
    if(roundChoice(rounds)===null||$('search').value==='synthesis'&&roundChoice(rounds)<2){actionError='invalid_rounds';render();return;}
    if(custom&&data.custom_capability?.available!==true){actionError=data.custom_capability?.code||'unsupported_runtime';render();return;}
    const snapshot=draftKey(),extra={request_id:crypto.getRandomValues(new Uint32Array(4)).reduce((s,n)=>s+n.toString(16).padStart(8,'0'),''),consent:'test',goal};
    let selected=null;actionError='';customErrors=[];
    if(custom){busy=true;render();try{
      const preview=await call('pickertargets',{custom_sites:$('custom-sites').value});
      if(!pageActive||draftKey()!==snapshot){actionError='selection_changed';return;}
      if(preview.valid!==true){customErrors=Array.isArray(preview.errors)?preview.errors:[{line:0,code:'invalid_hostname'}];return;}
      if(!validTargetPreview(preview)||customScope(preview.hosts,only,goal,language)===null)throw new Error('incomparable_result');
      selected={hosts:preview.hosts,only};extra.custom_sites=preview.hosts.join('\n');extra.custom_only=only?'1':'0';
    }catch(e){actionError=e.name==='AbortError'?'timed_out':e.message;return;}finally{busy=false;render();}}
    const search=$('search').value,extended=search==='profiles'&&$('extended').checked;
    const selection=planSelection({search,extended,goal,custom:selected,requested,rounds});
    const post={search,extended:extended?'1':'0',goal};if(requested!=='auto'){post.concurrency=requested;extra.concurrency=requested;}
    if(Number(rounds)>1){post.rounds=rounds;extra.rounds=rounds;}
    if(selected){post.custom_sites=[...selected.hosts].sort().join('\n');post.custom_only=selected.only?'1':'0';}
    busy=true;render();try{
      const plan=await call('pickerplan',post);
      if(!pageActive||draftKey()!==snapshot){actionError='selection_changed';return;}
      if(!validPoolPlan(plan,selection))throw new Error('incomparable_result');
      draftPlan={snapshot,post,plan};extra.plan_sha256=plan.plan_sha256;
    }catch(e){actionError=e.name==='AbortError'?'timed_out':e.message;return;}finally{busy=false;render();}
    ask($('search').value==='synthesis'?'pickersynthesize':($('extended').checked?'pickerextended':'pickerstart'),extra,
      selectionDescription(goal,$('search').value,language,selected)+' '+poolDescription(draftPlan.plan.concurrency_choice,language)+' '+(language==='ru'?`Прогонов подряд: ${rounds}. Начать временное переключение стратегий? Предыдущий отчёт подбора будет заменён; сохраните его при необходимости.`:`${rounds} sequential run(s). Temporarily switch strategies? The previous selection report will be replaced.`));
  });
  $('cancel').addEventListener('click',()=>void action('pickercancel',{id:data.job.id}));
  $('apply').addEventListener('click',()=>{if(outstanding&&outstanding.cmd!=='pickerapply')return;const j=data?.job,message=applyDescription(j,language,$('torrent-sites').checked);if(message===null){actionError='incomparable_result';render();return;}ask('pickerapply',{id:j.id,torrent_sites:$('torrent-sites').checked?'1':'0'},message);});
  $('refresh').addEventListener('click',()=>void poller.refresh());
  $('measured-select').addEventListener('change',async()=>{
    const job=data?.job,result=$('measured-select').value,request=++measuredRequest;
    const item=Array.isArray(job?.measured_results)?job.measured_results.find(row=>row?.id===result):null;
    measuredView=null;
    measuredStatus=item?'measurement_loading':'';
    render();
    if(!item||!authenticated||!pageActive)return;
    const current=()=>request===measuredRequest&&data?.job?.id===job.id&&pageActive&&authenticated;
    try{
      const v=await call('pickerresult',{id:job.id,result});
      if(!current())return;
      if(v?.id!==result||v.round!==item.round||typeof v.can_export!=='boolean'||
          v.profile?.name!==item.name||v.profile?.sample_type!==item.sample_type||
          !Array.isArray(v.profile.runs)||v.profile.runs.length!==(item.sample_type==='repeated'?2:1))
        throw new Error('measurement_unavailable');
      measuredView=v;measuredStatus='';
    }catch(e){
      if(current())measuredStatus=e.confirmed&&words[language][e.message]?e.message:'measurement_unavailable';
    }
    if(current())render();
  });
  function downloadJson(raw,filename){
    const a=document.createElement('a');
    const url=URL.createObjectURL(new Blob([raw],{type:'application/json'}));
    a.href=url;a.download=filename;a.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  $('measured-report').addEventListener('click',()=>{
    if($('measured-report').hidden||$('measured-report').disabled)return;
    const {id,round,profile}=measuredView;
    downloadJson(JSON.stringify({job_id:data.job.id,id,round,profile},null,2),`NFQWS2_MEASUREMENTS_${id}.json`);
  });
  $('measured-export').addEventListener('click',async()=>{
    if($('measured-export').hidden||$('measured-export').disabled)return;
    const id=data.job.id,result=measuredView.id;
    busy=true;measuredStatus='';render();
    try{
      const v=await call('pickerexport',{id,result});
      if(!pageActive||!authenticated||data?.job?.id!==id||measuredView?.id!==result)return;
      if(typeof v?.raw!=='string'||!v.raw.length||v.raw.length>4194304||v.filename!==`NFQWS2_MEASURED_${result}.json`)
        throw new Error('measurement_unavailable');
      downloadJson(v.raw,v.filename);
    }catch(e){
      measuredStatus=e.confirmed&&words[language][e.message]?e.message:'measurement_unavailable';
    }finally{
      busy=false;render();
    }
  });
  $('measured-import').addEventListener('click',()=>{
    if($('measured-import').hidden||$('measured-import').disabled)return;
    try{
      sessionStorage.setItem('nfqws-picker-import-v1',JSON.stringify({id:data.job.id,result:measuredView.id}));
      window.location.assign('/?picker-import=1');
    }catch{
      measuredStatus='measurement_unavailable';render();
    }
  });
  $('custom-check').addEventListener('click',async()=>{
    if(busy||data?.active)return;const input=$('custom-sites').value;busy=true;actionError='';customErrors=[];render();
    try{const preview=await call('pickertargets',{custom_sites:input});
      if(!pageActive||$('custom-sites').value!==input)return;
      if(!validTargetPreview(preview)){customErrors=preview.errors||[{line:0,code:'invalid_hostname'}];return;}
      sessionStorage.setItem('nfqws-site-check-targets-v1',JSON.stringify(preview.hosts));
      window.location.assign('/?site-check=1');
    }catch(e){actionError=e.message;}finally{busy=false;render();}
  });
  function shareDownload(raw,filename){
    const bytes=new TextEncoder().encode(raw);if(bytes.length<1||bytes.length>1048576)throw new Error('output_limit');
    sessionStorage.setItem('nfqws-share-download-v1',JSON.stringify({filename,media_type:'application/json',data_base64:btoa(Array.from(bytes,c=>String.fromCharCode(c)).join(''))}));
    window.location.assign('/?share-frank=1');
  }
  $('share-report').addEventListener('click',()=>{if(!data||data.active||!jobView(data.job,language).reportAvailable)return;
    try{shareDownload(JSON.stringify(data,null,2),'nfqws2-strategy-selection.json');}catch(e){actionError=e.message;render();}});
  $('share-export').addEventListener('click',async()=>{if(!data?.job?.can_export||data.active||busy)return;busy=true;actionError='';render();
    try{const v=await call('pickerexport',{id:data.job.id,torrent_sites:$('torrent-sites').checked?'1':'0'});shareDownload(v.raw,v.filename);}catch(e){actionError=e.message;}finally{busy=false;render();}});
  $('download').addEventListener('click',()=>{if(!data||data.active===true||!jobView(data.job,language).reportAvailable)return;downloadJson(JSON.stringify(data,null,2),'nfqws2-strategy-selection.json');});
  $('export').addEventListener('click',async()=>{busy=true;actionError='';render();try{const v=await call('pickerexport',{id:data.job.id,torrent_sites:$('torrent-sites').checked?'1':'0'});downloadJson(v.raw,v.filename);}catch(e){actionError=e.message;}finally{busy=false;render();}});
  const labels={ru:{title:'Подобрать стратегию',intro:'Проверки выполняются на этом роутере. После сравнения вернутся исходные настройки; лучший вариант можно применить отдельно.','device-title':'Возможности устройства','start-title':'Локальный подбор','goal-title':'Цель подбора','goal-all-label':'Все сервисы','goal-selected-label':'Выбранные сервисы','goal-help':'В режиме «Все сервисы» в первую очередь проверяются YouTube, Instagram, Discord и торрент-трекеры. Остальные сайты остаются дополнительным контролем. Для выбранных сервисов поиск и оценка сосредоточены на их доменах; общие проверки сохраняются для контроля ухудшений.',warning:'Во время смены профилей соединения могут кратковременно прерываться. DNS и сетевые настройки сохраняются. Закрытие страницы не останавливает работу; для отмены нажмите «Остановить и восстановить». Проверки в этой версии выполняются по IPv4.','extended-label':'Расширенный поиск, если готовые профили не улучшат результат','extended-help':'Проверяются раздельные и совместные варианты числа повторов TCP/QUIC. Правила отдельных сервисов и игр сохраняются; число попыток ограничено.','results-title':'Сравнение',explanation:'Для каждого профиля: предварительная проверка и обучение и два измерения. Показаны диапазоны успешных проверок. DNS проверяется отдельно и не влияет на рейтинг.','skipped-title':'Пропущенные варианты и причины',note:'Проверки доменов не подтверждают воспроизведение YouTube, голосовой чат Discord или загрузку ленты Instagram. После применения проверьте нужные функции в приложениях на своих устройствах.','confirm-submit':'Продолжить','confirm-dismiss':'Отмена'},en:{title:'Local strategy selection',intro:'Checks run on this router. Original settings are restored after comparison; applying a recommendation is a separate step.','device-title':'Device capacity','start-title':'Local selection','goal-title':'Selection goal','goal-all-label':'All services','goal-selected-label':'Selected services','goal-help':'All services prioritizes YouTube, Instagram, Discord and torrent trackers. Other sites remain additional controls. A selected-service search and ranking focus on those domains; overall checks still protect against regressions.',warning:'Connections may briefly interrupt while profiles change. DNS and network settings are preserved. Closing this page does not stop the job; use “Stop and restore” to cancel. This version measures IPv4.','extended-label':'Extend the search if catalog profiles do not improve the result','extended-help':'Tests bounded separate and combined TCP/QUIC repeat-count variants. Custom service and game rules are preserved.','results-title':'Comparison',explanation:'Each profile gets the same AUTO warmup and two recorded runs. Successful-check ranges are shown. DNS is tested separately and does not affect ranking.','skipped-title':'Skipped profiles and reasons',note:'Domain checks do not confirm YouTube playback, Discord voice or Instagram feeds. Verify the features you need in your apps after applying.','confirm-submit':'Continue','confirm-dismiss':'Cancel'}};
  Object.assign(labels.ru,{'search-label':'Способ поиска','search-synthesis':'Разработать стратегию','search-profiles':'Сравнить готовые профили','search-help':'Генератор стратегий проходит бета-тестирование. Он проверяет методы для HTTP, TLS и QUIC и уточняет поиск по результатам. Результаты прошлых запусков направляют поиск. В одной серии одинаковые поисковые сочетания исключаются; контрольные замеры исходной стратегии, соединения без обхода и лучших вариантов повторяются. Лучшие варианты проходят повторные замеры; улучшение не гарантируется. Каталог готовых стратегий не требуется. Проверки выполняются по IPv4.',explanation:'Предварительные замеры помогают выбрать варианты для повторной проверки. Итог сравнивается с вашей исходной стратегией и соединением без обхода. Применение выполняется отдельно.'});
  Object.assign(labels.en,{'search-label':'Search method','search-synthesis':'Develop a strategy','search-profiles':'Compare existing profiles','search-help':'The strategy generator is in beta. It tests methods for HTTP, TLS and QUIC and refines the search using the results. Previous results guide the search. Identical exploratory combinations are excluded within a series; the original strategy, pass-through and leading candidates get repeated control measurements. Leading candidates are measured repeatedly; improvement is not guaranteed. No strategy catalog is required. Checks use IPv4.',explanation:'Exploratory measurements select candidates for repeat checks. The result is compared with your original strategy and pass-through. Applying it is a separate step.'});
  Object.assign(labels.ru,{'rounds-title':'Количество прогонов','rounds-label':'Прогонов подряд: от 2 до 10','rounds-help':'Укажите число заранее: следующий прогон начнётся автоматически после восстановления настроек и новой проверки условий. При ошибке или остановке серия прекращается. Стратегия сама не применяется.'});
  Object.assign(labels.en,{'rounds-title':'Number of runs','rounds-label':'Consecutive runs: 2 to 10','rounds-help':'Choose the count before starting. Each next run begins automatically after restoring settings and rechecking conditions. An error or Stop ends the series. A strategy is never applied automatically.'});
  Object.assign(labels.ru,{'goal-torrents-label':'Торрент-трекеры','torrent-goal-help':'Цель «Торрент-трекеры» проверяет сайты NNMClub (nnmclub.to), RuTracker (rutracker.org), Rutor (rutor.info) и tapochek.net.','torrent-label':'Добавить торрент-трекеры','torrent-help':'Четыре сайта добавятся к области HTTPS собранного метода: nnmclub.to, rutracker.org, rutor.info, tapochek.net. Дополнение необязательно и выключено по умолчанию. Показатели выше получены для исходного комплекта до добавления дополнения; после добавления повторите проверку.'});
  Object.assign(labels.en,{'goal-torrents-label':'Torrent trackers','torrent-goal-help':'The Torrent trackers goal checks NNMClub (nnmclub.to), RuTracker (rutracker.org), Rutor (rutor.info) and tapochek.net.','torrent-label':'Add torrent tracker websites','torrent-help':'Extend the generated HTTPS method to nnmclub.to, rutracker.org, rutor.info and tapochek.net. Optional and off by default. The scores above describe the base strategy before this extension; repeat the checks after adding it.'});
  words.ru.torrent_sites_incompatible='Дополнение неприменимо к этому варианту HTTPS';words.en.torrent_sites_incompatible='This HTTPS variant cannot use the tracker extension';
  Object.assign(labels.ru,{'search-synthesis':'Разработать стратегию','custom-title':'Свои сайты','custom-enabled-label':'Добавить свои сайты к генерации','custom-sites-label':'До десяти доменов и публичных IPv4 суммарно, каждый с новой строки','custom-joint-label':'Вместе с выбранными сервисами','custom-only-label':'Только свои сайты; встроенные проверки — контроль','share-report':'Поделиться с Фрэнком','share-export':'Поделиться с Фрэнком','custom-check':'Проверить доступность','custom-examples':'Например: example.com, https://example.org или 8.8.8.8. Каждый адрес — с новой строки.','custom-help':'Проверяются корневые HTTPS-страницы по IPv4 с TLS 1.2 и 1.3. Для IP нужен сертификат, действительный для этого IP; домен не подставляется. Ошибка TLS сама по себе не доказывает блокировку. Правило IP может затрагивать другие HTTPS-сайты на том же адресе. Ответ сервера, включая 403, не означает доступность сайта. Telegram не участвует.'});
  Object.assign(labels.en,{'search-synthesis':'Develop a strategy','custom-title':'Custom sites','custom-enabled-label':'Add custom sites to generation','custom-sites-label':'Up to ten domains and public IPv4 addresses combined, one per line','custom-joint-label':'Together with selected services','custom-only-label':'Custom sites only; built-in checks are controls','share-report':'Share with Frank','share-export':'Share with Frank','custom-check':'Check availability','custom-examples':'Examples: example.com, https://example.org or 8.8.8.8. Enter one address per line.','custom-help':'Checks root HTTPS pages over IPv4 with TLS 1.2 and 1.3. An IP requires a certificate valid for that IP; no domain is substituted. A TLS failure alone does not establish blocking. An IP rule can affect other HTTPS sites at the same address. A server response, including 403, does not mean site access. Telegram is excluded.'});
  Object.assign(labels.ru,{'pool-title':'Одновременные запросы','pool-value-label':'Число запросов','pool-help':'Это число одновременных проверок соединения. Обычно достаточно 10–100. Большие значения не гарантируют ускорения подбора.'});
  Object.assign(labels.en,{'pool-title':'Simultaneous requests','pool-value-label':'Request count','pool-help':'This is the number of simultaneous connection checks. Usually 10–100 is enough. Larger values do not guarantee faster selection.'});
  Object.assign(labels.ru,{'result-columns-label':'Колонки результатов','result-columns-auto':'Авто'});
  Object.assign(labels.en,{'result-columns-label':'Result columns','result-columns-auto':'Auto'});
  $('language').addEventListener('click',()=>{language=language==='ru'?'en':'ru';document.documentElement.lang=language;$('language').textContent=language==='ru'?'EN':'RU';for(const [id,value]of Object.entries(labels[language]))text(id,value);showResultColumnCount();render();});
  let authenticated=false;
  window.addEventListener('pagehide',()=>{pageActive=false;supplementStatusCurrent=false;supplement.invalidate();pending=null;measuredRequest++;measuredStatus='';$('confirmation').hidden=true;poller.stop();});
  window.addEventListener('pageshow',()=>{pageActive=true;if(authenticated)poller.start();});
  void (async()=>{try{const s=await call('status');csrf=s.csrf_token;authenticated=true;poller.start();}catch(e){text('error',t(e.message));}})();
}
