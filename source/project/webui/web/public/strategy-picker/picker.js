import {MetricsHistory,PickerStatusPoller} from './metrics.js';
import {customMeasurements,customComparison,customScope,targetErrors,validTargetPreview} from './custom.js';
import {poolChoice,poolDescription,recordedPool,planSelection,validPoolPlan,roundChoice} from './concurrency.js';

// Both the standalone page and the PHP entry load this module from strategy-picker/.
const panelBase = /^https?:/.test(import.meta.url) ? new URL('../', import.meta.url).pathname : '/';
const mainServices=['youtube','discord','instagram'];
const services=[...mainServices,'torrents'];
const mainGoal=mainServices.join(',');

export function addonNotice(job,language='ru'){
  if(job?.state!=='applied'||!job.torrent_sites)return '';
  return language==='ru'?'Добавлено дополнение «Торрент-трекеры». Показатели относятся к исходному комплекту без дополнения; после добавления повторите проверку.':'The tracker extension was added. The scores describe the base strategy before this extension; repeat the checks after adding it.';
}
export function jobView(job,language='ru'){
  const w=words[language],state=job?.state,finished=['completed','applied'].includes(state);
  const stopped=['failed','cancelled','interrupted','recovery_required'].includes(state);
  const phase=stopped?(state==='recovery_required'&&job?.can_restart===true?w.restart_available:w[state]):
    (Object.hasOwn(w,job?.phase)?w[job.phase]:job?w.checking:'');
  const noWinner=stopped?phase:state==='applied'?w.applied:state==='completed'?
    (job.generation?.verified?(language==='ru'?'Исходная стратегия сохранена. Собранный комплект доступен для скачивания.':'Original retained. The generated kit is available to download.'):w.none):'';
  return {phase,noWinner,showWinner:finished&&job.restored===true,reportAvailable:finished||stopped};
}
export function profileLabel(profile,language='ru'){
  if(profile?.name!=='Собранная стратегия · повторная проверка')return profile?.name||'';
  const r=profile.components,plain=r&&['http','tls','quic'].every(k=>r[k]?.method==='pass')&&(!r.overrides||r.overrides.length===0);
  return language==='ru'?(plain?'Собранная стратегия · без методов обхода · повторная проверка':'Собранная стратегия · итоговая повторная проверка'):
    (plain?'Assembled strategy · no bypass methods · repeat verification':'Assembled strategy · final repeat verification');
}
export function resultCardTitle(card,language='ru'){
  const name=card.profile.name,ru=language==='ru';
  const titles={
    'Исходная стратегия · контроль':ru?'Исходная стратегия':'Original strategy',
    'Стоковая стратегия · контроль':ru?'Стоковая стратегия':'Stock strategy',
    'Без методов обхода · контроль':ru?'Без обхода':'Without bypass',
    'Лучшие варианты · повторная проверка':ru?'Вариант · повторная проверка':'Variant · repeat check',
    'Собранная стратегия · повторная проверка':ru?'Собранная стратегия':'Assembled strategy',
  };
  const label=titles[name]??(/^Вариант обхода · \d+$/.test(name)?(ru?'Вариант':'Variant'):profileLabel(card.profile,language));
  return `${card.round}-${card.number} ${label||(ru?'Вариант':'Variant')}`;
}
export function isFullRatio({low,high,total}){
  return total>0&&low===total&&high===total;
}
export function savedResultCards(report,job,round,catalog){
  if(report?.id!==job||report.round!==round||!Array.isArray(report.cards)||!report.cards.length)return null;
  const known=new Map(catalog.filter(item=>item?.round===round).map(item=>[item.id,item]));
  const ids=new Set(),cards=[];
  for(const [index,entry] of report.cards.entries()){
    if(!entry||typeof entry.id!=='string'||!/^[a-f0-9]{32}$/.test(entry.id)||ids.has(entry.id)||
      entry.number!==index+1||typeof entry.can_export!=='boolean')return null;
    const expected=known.get(entry.id),profile=entry.profile;
    if(!expected||typeof profile?.name!=='string'||profile.name!==expected.name||profile.sample_type!==expected.sample_type||
      !Array.isArray(profile.runs)||profile.runs.length!==(expected.sample_type==='repeated'?2:1))return null;
    ids.add(entry.id);
    cards.push({...entry,round,can_export:entry.can_export&&expected.document_available===true});
  }
  return cards;
}
export function retryHint(language='ru'){
  return language==='ru'?'Результаты первых проверок учитываются, когда начинаются второй, третий и следующие прогоны. Улучшение не гарантируется.':'The second, third and later runs build on earlier measurements. Improvement is not guaranteed.';
}
export function goalLabel(goal='all',language='ru'){
  const names={youtube:'YouTube',discord:'Discord',instagram:'Instagram',torrents:language==='ru'?'Торрент-трекеры':'Torrent trackers'};
  return goal==='all'?(language==='ru'?'все сервисы':'all services'):goal.split(',').map(s=>names[s]||s).join(' + ');
}
export function selectionDescription(goal,search,language='ru',custom=null){
  if(custom){const scope=customScope(custom.hosts,custom.only,goal,language);return scope===null?null:
    (language==='ru'?'Создание стратегии. ':'Creating a strategy. ')+scope;}
  const scope=goalLabel(goal,language);
  const method=language==='ru'?(search==='synthesis'?'Создать новую стратегию':'Сравнить готовые стратегии'):(search==='synthesis'?'Create a new strategy':'Compare existing strategies');
  return method+'. '+(language==='ru'?'Цель: ':'Goal: ')+scope+'.';
}
export function searchDescription(search,language='ru'){
  if(search!=='synthesis')return language==='ru'?'Роутер сравнит вашу текущую стратегию, стандартную и подходящие варианты из каталога.':'The router compares your current strategy with the default and compatible strategies from the catalog.';
  return language==='ru'?'Создание новой стратегии пока в бета-версии. Роутер пробует разные настройки и повторно проверяет лучшие варианты. Улучшение не гарантируется. Проверки идут по IPv4.':'Creating new strategies is in beta. The router tries different settings and checks the most promising options again. Results may vary. Tests use IPv4.';
}
export function reportDescription(search,language='ru'){
  if(search!=='synthesis')return language==='ru'?'Каждую стратегию проверили дважды. В таблице показано, сколько проверок прошло успешно. Проверка DNS не влияет на сравнение.':'Each strategy was measured twice. The table shows how many checks passed. DNS is checked separately and has no effect on the comparison.';
  return language==='ru'?'Роутер повторно проверяет лучшие варианты и сравнивает итог с вашей исходной стратегией и соединением без обхода.':'The router checks promising strategies again and compares the result with your original strategy and a connection without bypass.';
}
export function generationSummary(generation,language='ru'){
  const fromZero=generation?.from_zero?.eligible===true;
  const versusCurrent=generation?.verified===true&&generation?.versus_current?.eligible===true;
  if(language==='ru')return fromZero?
    'Повторные проверки показали улучшение по выбранной цели по сравнению с соединением без обхода. '+
      (versusCurrent?'Она улучшила результат для выбранных сервисов по сравнению с вашей исходной стратегией.':'Ваша исходная стратегия сохранена. Улучшение по сравнению с ней не подтвердилось.'):
    'Проверки пока не показали, что новая стратегия работает лучше соединения без обхода.';
  return fromZero?
    'Repeated checks showed an improvement for the selected goal over the connection without bypass. '+
      (versusCurrent?'It also improved results for the selected services over your original strategy.':'The router kept your original strategy. The new strategy did not show an improvement over it.'):
    'The checks have not shown an improvement over the connection without bypass.';
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
  const base=language==='ru'?`Заменить текущую стратегию этим вариантом? Роутер сохранит исходные файлы. Цель проверок по IPv4 — ${goal}.`:`Replace your current strategy with this one? The router will keep the original files. The goal of the IPv4 checks was ${goal}.`;
  const addon=torrentSites?(language==='ru'?' Дополнение для торрент-трекеров будет добавлено без отдельного измерения.':' The tracker extension is not separately measured.'):'';
  return base+(notice?' '+notice:'')+addon;
}
function recoveryBlocked(j){return j?.state==='recovery_required'&&j.can_restart!==true;}
const words={ru:{start:'Начать подбор',cancel:'Остановить и восстановить',refresh:'Обновить состояние',apply:'Применить этот вариант',download:'Скачать отчёт',baseline:'Исходная стратегия',eligible:'Подтверждённое улучшение по выбранной цели',no_improvement:'Улучшение не подтверждено',tls_regression:'Некоторые защищённые соединения стали работать хуже',youtube_regression:'Меньше проверок YouTube прошли успешно',incomparable_result:'Сравнить результаты не удалось',complete:'Подбор завершён',catalog:'Подготовка профилей',dns:'Проверка DNS',switching:'Переключение стратегии',warming:'Проверка соединения перед замером',measuring_1:'Первое измерение',measuring_2:'Повторное измерение',restoring:'Восстановление исходного состояния',applying:'Применение выбранной стратегии',applied:'Стратегия применена',backup:'Резервная копия',restored:'Исходные настройки восстановлены.',notrestored:'Роутер ещё не подтвердил возврат настроек.',none:'Улучшение не подтвердилось. Роутер вернул исходную стратегию.',best:'Рекомендуемый вариант: ',not_installed:'Сначала установите DPI Detector кнопкой в основной панели.',busy:'Устройство занято другой операцией. Дождитесь завершения.',insufficient_memory:'Недостаточно свободной памяти для безопасной проверки.',insufficient_space:'Недостаточно места для резервной копии и ресурсов.',source_changed:'Настройки изменены вне подбора. Чужие изменения не перезаписаны; требуется проверка.',recovery_required:'Роутер не подтвердил возврат настроек. Скачайте отчёт и отправьте его Фрэнку. Новый подбор пока недоступен.',split_mode_active:'Для подбора сначала включите общий режим стратегий.',all_mode_not_supported:'Выберите режим «Авто» или «Список». Режим «Всё» в подборе не используется.',cancelled:'Подбор остановлен.',timed_out:'Проверка не завершилась за отведённое время.',interrupted:'Проверка была прервана.',goal_no_improvement:'Улучшение выбранных сервисов не подтверждено',goal_regression:'Ухудшение выбранного сервиса',failed:'Подбор не завершён. Сохраните отчёт для диагностики.',invalid_synthesis_recipe:'Не удалось собрать вариант стратегии. Подбор остановлен. Сохраните отчёт.',unsupported_abi:'Для этой модели роутера подбор недоступен.',unsupported_runtime:'Не удалось запустить проверку с выбранными параметрами. Уменьшите число запросов; если ошибка повторится, сохраните отчёт.',storage_unavailable:'Хранилище подбора недоступно. Сохраните имеющийся отчёт и проверьте накопитель.',detector_failed:'DPI Detector не завершил измерение. Сохраните отчёт.',service_start_failed:'Не удалось запустить службу. Сохраните отчёт.',service_stop_failed:'Не удалось остановить службу. Сохраните отчёт.',service_check_failed:'Не удалось подтвердить работу службы. Сохраните отчёт.',lua_trust:'Роутер пропустил стратегию, потому что её скрипты требуют разрешения.',unresolved_profile_resource:'Не удалось найти файлы, нужные для этой стратегии.',choose_goal:'Выберите хотя бы один сервис.',stale_state:'Этот отчёт больше не подходит к текущим настройкам. Запустите подбор снова.',auth:'Войдите в основную панель и откройте подбор снова.'},en:{start:'Start selection',cancel:'Stop and restore',refresh:'Refresh status',apply:'Apply this strategy',download:'Download report',baseline:'Original strategy',eligible:'Confirmed improvement for the selected goal',no_improvement:'No confirmed improvement',tls_regression:'Some secure connections got worse',youtube_regression:'Fewer YouTube checks passed',incomparable_result:'Results could not be compared',complete:'Selection complete',catalog:'Preparing profiles',dns:'Checking DNS',switching:'Switching strategy',warming:'Checking the connection before measuring',measuring_1:'First measurement',measuring_2:'Repeat measurement',restoring:'Restoring original state',applying:'Applying strategy',applied:'Strategy applied',backup:'Backup',restored:'Original settings restored.',notrestored:'The router has yet to confirm that it restored your settings.',none:'The router kept your original strategy because the checks showed no clear improvement.',best:'Recommended strategy: ',not_installed:'Install DPI Detector from the main panel first.',busy:'Another operation is using the device.',insufficient_memory:'Not enough available memory.',insufficient_space:'Not enough storage for backup and resources.',source_changed:'Settings changed outside this operation; foreign changes were preserved.',recovery_required:'The router could not confirm that it restored the settings. Download the report and share it with Frank. Starting a new search is unavailable for now.',split_mode_active:'Switch to common strategy mode first.',all_mode_not_supported:'Use AUTO or LIST mode; ALL is excluded.',cancelled:'Search stopped.',timed_out:'Time limit reached.',interrupted:'Interrupted.',goal_no_improvement:'No confirmed improvement for selected services',goal_regression:'A selected service regressed',failed:'Selection did not finish. Save the diagnostic report.',invalid_synthesis_recipe:'Could not build a strategy variant. Selection stopped. Save the report.',unsupported_abi:'Strategy search is unavailable for this router model.',unsupported_runtime:'The checks could not start with these settings. Reduce the request count; if this recurs, share the report with Frank.',storage_unavailable:'Selection storage is unavailable. Save the report and check storage.',detector_failed:'DPI Detector did not finish the measurement. Save the report.',service_start_failed:'The service could not start. Save the report.',service_stop_failed:'The service could not stop. Save the report.',service_check_failed:'Service operation could not be confirmed. Save the report.',lua_trust:'The router skipped this strategy because its scripts require permission.',unresolved_profile_resource:'Files needed by this strategy are missing.',choose_goal:'Select at least one service.',stale_state:'This report no longer matches your current settings. Start a new search.',auth:'Sign in to the main panel, then reopen this page.'}};
Object.assign(words.ru,{synthesis_setup:'Подготовка подбора',discovering:'Проверка методов и параметров',assembling:'Сборка правил по результатам',zero_baseline:'Стратегия временно отключена, чтобы сравнить обычное соединение с работой обхода. После проверки подбор продолжится.',synthesis_lua_unavailable:'Стандартные Lua не совпадают с проверенной версией пакета. Генерация не начата.',synthesis_unverified:'Для этой стратегии нет подтверждённой повторной проверки.',retested:'Вариант проверен повторно',protocol_regression:'Часть ранее успешных проверок перестала проходить',export:'Скачать стратегию с файлами'});
Object.assign(words.en,{synthesis_setup:'Preparing strategy generation',discovering:'Testing methods and parameters',assembling:'Assembling measured rules',zero_baseline:'Pass-through control',synthesis_lua_unavailable:'Standard Lua does not match the verified package. Generation has not started.',synthesis_unverified:'This strategy has no confirmed repeat validation.',retested:'Retested candidate',protocol_regression:'Some previously successful checks stopped passing',export:'Download strategy with files'});
words.ru.stock_baseline='Штатная стратегия из пакета';words.en.stock_baseline='Package default strategy';
Object.assign(words.ru,{invalid_custom_targets:'Проверьте список своих сайтов.',request_conflict:'Этот запрос уже связан с другим набором целей. Обновите отчёт и начните новый подбор.',selection_changed:'Выбор изменился. Проверьте его и начните снова.',custom_regression:'Ухудшение проверки своего сайта',native_regression:'Ухудшение встроенных контрольных проверок',custom_budget_unavailable:'Не удалось подготовить все проверки. Измените список сайтов и повторите подбор.',synthesis_rule_limit:'Не удалось собрать все цели в допустимое число правил. Неполный вариант не предлагается.'});
Object.assign(words.en,{invalid_custom_targets:'Check the custom site list.',request_conflict:'This request already identifies different goals. Refresh the report and start a new search.',selection_changed:'Your selection changed. Review it and start again.',custom_regression:'A custom site check regressed',native_regression:'Built-in control checks regressed',custom_budget_unavailable:'A safe time budget is unavailable for these checks.',synthesis_rule_limit:'The complete target set exceeds the rule limit. No partial strategy is offered.'});
Object.assign(words.ru,{request_unconfirmed:'Ответ не получен. Работа на роутере может продолжаться. Обновите статус или повторите тот же запрос.',retry_request:'Повторить тот же запрос'});
Object.assign(words.en,{request_unconfirmed:'No response was received. Work on the router may continue. Refresh status or retry the same request.',retry_request:'Retry the same request'});
Object.assign(words.ru,{invalid_pool:'Введите целое число от 1 до 1000000 без пробелов и ведущих нулей.',concurrency_budget_unavailable:'Не удалось подготовить проверки с этим числом запросов. Уменьшите его и повторите.',plan_changed:'Условия проверки изменились. Выберите параметры и подтвердите новый план.'});
Object.assign(words.en,{invalid_pool:'Enter an integer from 1 to 1000000 without spaces or leading zeros.',concurrency_budget_unavailable:'This request pool cannot cover every target within the safe time limit.',plan_changed:'The test conditions changed. Review the selection and confirm a new plan.'});
words.ru.invalid_rounds='Введите целое число прогонов от 2 до 10.';words.en.invalid_rounds='Enter a whole number of runs from 2 to 10.';
Object.assign(words.ru,{
  checking:'Идёт проверка',
  restart_available:'Подбор остановлен. Можно начать новый.',
  preparing:'Готовим подбор',
  profiles:'Подготовка стратегий',
  series_between:'Подготовка следующего прогона',
  details_unavailable:'Подробности смотрите в отчёте.',
  output_limit:'Файл слишком большой для отправки. Скачайте его отдельно.',
  picker_resource_limit:'Роутер не смог проверить все файлы стратегий перед подбором. Проверьте количество и размер списков и файлов стратегий.',
  request_conflict:'Выбор для этого запуска изменился. Обновите состояние и начните новый подбор.',
  invalid_request:'Не удалось выполнить действие. Обновите состояние и попробуйте снова.',
  admission_closed:'Роутер сейчас не готов к подбору. Проверьте состояние и попробуйте снова.',
  admission_busy:'Подбор уже запускается. Обновите состояние.',
  guard_lost:'Роутер потерял контроль над проверкой. Дождитесь сообщения о восстановлении.',
});
Object.assign(words.en,{
  checking:'Check in progress',
  restart_available:'The search stopped. You can start a new one.',
  preparing:'Preparing the search',
  profiles:'Preparing strategies',
  series_between:'Preparing the next run',
  details_unavailable:'See the report for details.',
  output_limit:'The file is too large to share here. Download it separately.',
  picker_resource_limit:'The router could not check all strategy files before starting. Check the number and size of strategy files and lists.',
  request_conflict:'The selection for this run changed. Refresh status and start a new search.',
  invalid_request:'The action could not be completed. Refresh status and try again.',
  admission_closed:'The router is not ready for a search. Refresh status and try again.',
  admission_busy:'The search is starting. Refresh status.',
  guard_lost:'The router lost control of the check. Wait for the restoration status.',
});
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
words.ru.auth='Войдите в основную панель заново и обновите страницу.';words.en.auth='Your session expired. Sign in on the main panel and reload this page.';
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
  let csrf='',data=null,busy=false,language='ru',actionError='',pending=null,goalLoaded=false,customLoaded=false,customErrors=[],pageActive=true;const $=id=>document.getElementById(id);const t=key=>Object.hasOwn(words[language],key)?words[language][key]:words[language].details_unavailable;
  let poolLoaded=false,roundsLoaded=false,draftPlan=null,timingJob=null,timingReceived=0;$('pool-value').value='100';$('rounds-value').value='2';
  let resultJob=null,resultRound=null;
  const savedCards=new Map();
  let ownedWindow=null,windowTimer=null;
  const randomId=()=>crypto.getRandomValues(new Uint32Array(4)).reduce((id,value)=>id+value.toString(16).padStart(8,'0'),'');
  function forgetWindow(){
    if(windowTimer!==null)clearInterval(windowTimer);
    windowTimer=null;
    ownedWindow=null;
  }
  function reportWindow(presence){
    if(!ownedWindow||!authenticated||!csrf)return;
    const url=panelBase+'index.php';
    const body=new URLSearchParams({cmd:'pickerwindow',csrf_token:csrf,...ownedWindow,presence});
    if(presence==='closed'){
      try{if(window.navigator?.sendBeacon?.(url,body))return;}catch{/* Try the keepalive transport. */}
    }
    const signal=presence==='open'?AbortSignal.timeout?.(15000):undefined;
    void fetch(url,{method:'POST',credentials:'same-origin',body,keepalive:presence==='closed',signal}).catch(()=>{});
  }
  function observeWindow(result){
    if(ownedWindow&&result?.job?.request_id===ownedWindow.request_id&&!result.active)forgetWindow();
  }
  const requestedPool=()=>{const v=$('pool-value').value;return v==='auto'?null:poolChoice(v);};
  function text(id,value){$(id).textContent=value;}
  const metrics=new MetricsHistory();let metricsEpoch=0;
  function renderMetrics(){const v=metrics.view(performance.now(),language);for(const key of ['cpu','memory','temperature','freshness'])text('metric-'+key,v[key]);$('live-metrics').classList.toggle('stale',v.stale);const j=data?.job;if(j!==timingJob){timingJob=j;timingReceived=performance.now();}text('remaining',remainingTime(j,data?.active,(performance.now()-timingReceived)/1000,language));}
  async function call(cmd,extra={}){
    const p=new URLSearchParams({cmd,...(cmd==='status'?{}:{csrf_token:csrf}),...extra});
    const controller=new AbortController();
    const timeout=controller?setTimeout(()=>controller.abort(),15000):null;
    try{
    const r=await fetch(panelBase+'index.php',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:p,...(controller?{signal:controller.signal}:{})});
    if(r.status===401||r.status===403){authenticated=false;forgetWindow();pending=null;$('confirmation').hidden=true;if(data)data={...data,error:'auth'};poller.stop();render();throw new Error('auth');}
    const v=await r.json();if(!r.ok||v.error){const error=new Error(v.error||'failed');error.confirmed=true;throw error;}return v;
    }finally{if(timeout!==null)clearTimeout(timeout);}
  }
  const mutationKey='nfqws-picker-pending-v1';
  function validMutation(v){
    if(!v||!['pickerstart','pickerextended','pickersynthesize','pickerapply','pickercancel'].includes(v.cmd)||!v.extra||typeof v.extra!=='object')return false;
    const e=v.extra;let keys=Object.keys(e).sort().join(',');
    if(['pickerapply','pickercancel'].includes(v.cmd))return /^[a-f0-9]{32}$/.test(e.id||'')&&
      (v.cmd==='pickercancel'?keys==='id':keys==='id,torrent_sites'&&['0','1'].includes(e.torrent_sites)||keys==='id,result'&&/^[a-f0-9]{32}$/.test(e.result||''));
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
    observeWindow(result);
    if(!outstanding)return;
    const {cmd,extra}=outstanding,j=result?.job;
    if((extra.request_id&&j?.request_id===extra.request_id)||j?.id===extra.id&&
      (cmd==='pickercancel'&&!result.active||cmd==='pickerapply'&&(!extra.result||j.applied_result===extra.result)&&
        ['applying','applied','failed','cancelled','interrupted','recovery_required'].includes(j.state))){
      rememberMutation(null);if(actionError==='request_unconfirmed')actionError='';
    }
  }
  function draftKey(){return JSON.stringify([language,$('search').value,$('extended').checked,$('goal-main').checked,$('goal-all').checked,
    ...services.map(s=>$('goal-'+s).checked),$('custom-enabled').checked,$('custom-only').checked,$('custom-sites').value,$('pool-value').value,$('rounds-value').value]);}
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
  function renderProfile(card,job,terminal,apply){
    const profile=card.profile;
    const row=document.createElement('article');
    row.className='result'+(profile.name==='Собранная стратегия · повторная проверка'?' assembled-final':'');
    const title=document.createElement('h3');
    title.textContent=resultCardTitle(card,language);
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
    const displayedServices=!job.goal||job.goal==='all'?services:job.goal.split(',');
    for(const service of displayedServices){
      const measured=ranges(profile.runs,service);
      const serviceRow=document.createElement('tr'),name=document.createElement('th');
      name.scope='row';
      name.textContent=goalLabel(service,language);
      serviceRow.append(name);
      if(measured.length){
        for(const range of measured){
          const cell=document.createElement('td');
          cell.textContent=formatRatio(range);if(isFullRatio(range))cell.className='result-complete';serviceRow.append(cell);
        }
      }else{
        const cell=document.createElement('td');
        cell.colSpan=4;cell.textContent=ru?'Нет замеров':'Not measured';serviceRow.append(cell);
      }
      body.append(serviceRow);
    }
    const foot=document.createElement('tfoot'),totalsRow=document.createElement('tr'),totalsCell=document.createElement('td');
    foot.hidden=!$('result-show-totals').checked;
    totalsCell.colSpan=5;
    const totalsTitle=document.createElement('span');
    totalsTitle.className='totals-title';totalsTitle.textContent=ru?'Все сайты':'All sites';
    const metrics=document.createElement('div');
    metrics.className='metrics';
    for(const range of ranges(profile.runs)){
      const value=document.createElement('span');
      value.textContent=protocolLabels[range.key]+': ';
      const ratio=document.createElement('span');
      ratio.textContent=formatRatio(range);if(isFullRatio(range))ratio.className='result-complete';
      value.append(ratio);metrics.append(value);
    }
    if(!metrics.childNodes.length)metrics.textContent=language==='ru'?'Показатели недоступны':'Metrics unavailable';
    totalsCell.append(totalsTitle);totalsCell.append(metrics);totalsRow.append(totalsCell);foot.append(totalsRow);
    table.append(head);table.append(body);table.append(foot);row.append(table);
    if(Array.isArray(job.custom_hosts)){
      const v=customMeasurements(profile.custom_runs),label=document.createElement('p');
      label.className='custom-metrics';
      label.textContent=v?(language==='ru'?`Свои сайты · ${v.repeats===2?'успешно в обоих замерах':'предварительный замер'}: ${v.stable}/${v.total}. Сервер ответил: ${v.responded}/${v.total}.`:
        `Custom sites · ${v.repeats===2?'successful in both runs':'exploratory sample'}: ${v.stable}/${v.total}. Server answered: ${v.responded}/${v.total}.`):t('incomparable_result');
      row.append(label);
      for(const site of v?.rows||[]){
        const line=document.createElement('p'),ratio=c=>`${c.low===c.high?c.low:c.low+'–'+c.high}/1`;
        line.className='custom-metrics';
        line.textContent=`${site.host}: TLS 1.2 ${ratio(site.tls12)} · TLS 1.3 ${ratio(site.tls13)}`;
        row.append(line);
      }
    }
    const reason=profile.error||(profile.rank?.eligible?'eligible':profile.rank?.reason)||(profile.sample_type==='exploratory'?'exploratory':'failed');
    if(reason!=='exploratory'){
      const why=document.createElement('p');
      why.textContent=t(reason);
      row.append(why);
    }
    if(terminal){
      const actions=document.createElement('div');actions.className='result-actions';
      const button=document.createElement('button');button.type='button';button.className='result-apply';
      button.disabled=!apply;button.textContent=ru?'Применить':'Apply';
      button.setAttribute('aria-label',button.textContent+' '+card.round+'-'+card.number);
      if(apply)button.addEventListener('click',apply);
      else button.title=ru?'Стратегия для этого результата сейчас недоступна.':'The strategy for this result is currently unavailable.';
      actions.append(button);row.append(actions);
    }
    return row;
  }
  function formatRatio({low,high,total}){
    return `${low===high?low:`${low}–${high}`}/${total}`;
  }
  function savedRoundCards(job,round){
    const catalog=job.measured_results.filter(item=>item?.round===round);
    const signature=JSON.stringify([job.id,job.state,job.restored,catalog]);
    const previous=savedCards.get(round);
    if(previous?.signature===signature)return previous;
    const report={signature,cards:null,error:false};
    savedCards.set(round,report);
    const current=()=>savedCards.get(round)===report&&pageActive&&authenticated&&!data?.active&&data.job?.id===job.id;
    void (async()=>{
      try{
        const response=await call('pickerreport',{id:job.id,round:String(round)});
        if(!current())return;
        report.cards=savedResultCards(response,job.id,round,catalog);
        report.error=!report.cards;
      }catch{
        if(current())report.error=true;
      }
      if(current()&&resultRound===round)render();
    })();
    return report;
  }
  function canApplyCard(job){
    return pageActive&&authenticated&&!busy&&!outstanding&&!data?.active&&!data?.error&&
      data?.job?.id===job.id&&data.job.restored===true;
  }
  function renderResultCards(job,profiles,terminal){
    const defaultRound=job.series?.selected||job.series?.current||1;
    const measured=terminal&&Array.isArray(job.measured_results)?job.measured_results:[];
    const rounds=[...new Set(measured.map(item=>item?.round))]
      .filter(round=>Number.isInteger(round)&&roundChoice(String(round))!==null).sort((a,b)=>a-b);
    if(!rounds.includes(resultRound))resultRound=rounds.includes(defaultRound)?defaultRound:rounds[0]??defaultRound;
    const ru=language==='ru',nav=$('result-rounds');
    nav.replaceChildren();
    for(const round of rounds){
      const button=document.createElement('button');
      button.type='button';button.textContent=(ru?'Прогон ':'Run ')+round;
      button.setAttribute('aria-pressed',String(round===resultRound));button.disabled=busy;
      button.addEventListener('click',()=>{resultRound=round;render();});
      nav.append(button);
    }
    nav.setAttribute('aria-label',ru?'Прогоны':'Runs');
    $('result-toolbar').hidden=!rounds.length;
    const report=rounds.length&&authenticated&&pageActive&&!data.error?savedRoundCards(job,resultRound):null;
    const cards=report?.cards??(resultRound===defaultRound?profiles.map((profile,index)=>({number:index+1,round:defaultRound,profile})):[]);
    const result=$('results');result.replaceChildren();
    for(const card of cards){
      let apply=null;
      if(terminal&&canApplyCard(job)){
        if(card.id&&card.can_export)apply=()=>{
          if(resultRound!==card.round||!canApplyCard(job)||
            !data.job.measured_results?.some(item=>item.id===card.id&&item.round===card.round&&item.document_available===true))return;
          void action('pickerapply',{id:job.id,result:card.id});
        };
        else if(!report&&card.profile===winnerProfile(job)){
          const message=applyDescription(job,language);
          if(message!==null)apply=()=>{
            if(canApplyCard(job)&&data.job.winner===job.winner&&applyDescription(data.job,language)===message)
              void action('pickerapply',{id:job.id,torrent_sites:'0'});
          };
        }
      }
      result.append(renderProfile(card,job,terminal,apply));
    }
    const message=report?.error?t('measurement_unavailable'):
      report&&!report.cards?(ru?'Загружаются результаты прогона.':'Loading run results.'):'';
    text('result-feed-status',message);$('result-feed-status').hidden=!message;
  }
  function render(){
    // Clear actionable output before inspecting a refreshed report. A malformed
    // response must never leave the previous recommendation or approval visible.
    for(const id of ['generation','matrix','measured-goal','explanation','custom-summary','result-feed-status'])text(id,'');$('result-feed-status').hidden=true;$('custom-summary').hidden=true;
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
    text('limits',b?(language==='ru'?`До ${b.concurrency} одновременных проверок. Роутер сравнит сохранённые стратегии и до трёх дополнительных вариантов.`:`Up to ${b.concurrency} simultaneous checks. The router compares saved strategies and up to three additional options.`):'');
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
      (language==='ru'?`Роутер проверит и другие сайты, чтобы заметить ухудшения.`:`The router also checks other sites to spot any decline.`):t(data.custom_capability?.code||'unsupported_runtime')):'');
    text('search-help',searchDescription($('search').value,language));
    $('extended-control').hidden=synthesis;$('extended-help').hidden=synthesis;
    if(synthesis&&b){const g=locked?(j.matrix||data.generator):data.generator,shown=custom&&customBudget?customBudget:b;text('limits',language==='ru'?`До ${shown.concurrency} одновременных проверок. Роутер попробует до ${g?.max_trials||8} вариантов и повторно проверит собранную стратегию.`:`Up to ${shown.concurrency} simultaneous checks. The router tries up to ${g?.max_trials||8} options and checks the resulting strategy again.`);}
    if(!locked&&requested!=='auto'&&!planned){
      const message=requested===null?t('invalid_pool'):(language==='ru'?`Выбрано до ${requested} одновременных проверок.`:`Up to ${requested} simultaneous checks selected.`);
      text('limits',message);if(custom)text('custom-budget',message);
    }
    if(!goalLoaded||locked){
      $('extended').checked=Boolean(j?.extended);
      const goal=locked?(j.goal||'all'):(outstanding?.extra.goal||mainGoal);
      $('goal-main').checked=goal===mainGoal;
      $('goal-all').checked=goal==='all';
      $('goal-selected').checked=goal!=='all'&&goal!==mainGoal;
      for(const service of services)$('goal-'+service).checked=goal==='all'||goal.split(',').includes(service);
      goalLoaded=true;
    }
    $('goals').disabled=busy||locked||Boolean(pending)||Boolean(outstanding)||customOnly;
    const allServices=$('goal-all').checked,mainPreset=$('goal-main').checked;
    $('goal-options').hidden=allServices||mainPreset||customOnly;
    for(const service of services){
      const option=$('goal-'+service);
      if(allServices||mainPreset)option.checked=allServices||mainServices.includes(service);
      option.disabled=allServices||mainPreset||customOnly;
    }
    $('start').disabled=busy||active||Boolean(pending)||Boolean(outstanding&&!outstanding.extra.request_id)||!data.detector.installed||Boolean(data.error)||recoveryBlocked(j)||requested===null||invalidCount||custom&&data.custom_capability?.available!==true;
    $('cancel').hidden=!active;$('cancel').disabled=busy||Boolean(data.error)||Boolean(outstanding&&outstanding.extra.id!==j?.id);$('extended').disabled=locked||busy||Boolean(pending)||Boolean(outstanding);
    $('progress-section').hidden=!j;$('results-section').hidden=!j||(validProfiles&&!profiles.length&&!j.measured_results?.length);
    for(const id of ['start','cancel','refresh','download'])text(id,t(id));if(outstanding?.extra.request_id)text('start',t('retry_request'));
    const jobCode=j?.state==='recovery_required'&&j.can_restart===true?null:j?.code;
    text('error',actionError?t(actionError):(jobCode?t(jobCode):(data.error?t(data.error):(!data.detector.installed?t(data.detector.code||'not_installed'):''))));
    $('download').hidden=data.active===true||!view?.reportAvailable;
    $('share-report').hidden=$('download').hidden;$('share-report').disabled=busy;
    $('round-help').hidden=!synthesis;
    const series=j?.series;text('series-status',series?(language==='ru'?
      `${active?'Серия выполняется':'Серия завершена или остановлена'}: прогон ${series.current} из ${series.total}. Завершено: ${series.completed}.`:
      `${active?'Series running':'Series finished or stopped'}: run ${series.current} of ${series.total}. Completed: ${series.completed}.`):'');
    if(active||resultJob!==j?.id){resultJob=j?.id;resultRound=null;savedCards.clear();}
    if(!j)return;
    text('phase',view.phase);text('current',profileLabel(profiles.find(p=>p.name===j.current_name)||{name:j.current_name},language));$('progress').value=j.progress||0;
    text('restore',j.state==='applied'?t('applied'):j.restored?t('restored'):
      !active||j.state==='restoring'?t('notrestored'):'');
    if(!validProfiles){$('results').replaceChildren();$('result-toolbar').hidden=true;
      text('error',t('incomparable_result'));text('result-feed-status',tradeoffNotice(j,null,language));$('result-feed-status').hidden=false;return;}
    text('measured-goal',(language==='ru'?(j.search==='synthesis'?'Отчёт генератора · цель: ':'Отчёт сравнения готовых профилей · цель: '):(j.search==='synthesis'?'Generation report · goal: ':'Existing-profile comparison · goal: '))+goalLabel(j.goal||'all',language));
    text('explanation',reportDescription(j.search,language));
    if(Array.isArray(j.custom_hosts))text('measured-goal',(language==='ru'?'Отчёт генератора · ':'Generation report · ')+(customScope(j.custom_hosts,j.custom_only,j.goal||'all',language)||t('incomparable_result')));
    const comparison=customComparison(j);if(comparison){$('custom-summary').hidden=false;text('custom-summary',language==='ru'?
      `Свои сайты · до: ${comparison.before}/${comparison.total} → после: ${comparison.after}/${comparison.total}. Успешный HTTPS-ответ подтверждён в обоих замерах, отдельно для TLS 1.2 и 1.3.`:
      `Custom sites · before: ${comparison.before}/${comparison.total} → after: ${comparison.after}/${comparison.total}. Root HTTPS success in both runs, separately for TLS 1.2 and 1.3.`);}
    text('matrix',j.matrix?(language==='ru'?`Проверено ${j.matrix.tested} из ${j.matrix.max_trials} вариантов.${j.matrix.stopped_by_budget?' Достигнут предел проверок для этого прогона.':''}`:`Tested ${j.matrix.tested} of ${j.matrix.max_trials} options.${j.matrix.stopped_by_budget?' The run reached its test limit.':''}`):'');
    text('generation',j.generation&&view.showWinner?generationSummary(j.generation,language):'');
    renderResultCards(j,profiles,!active&&view.reportAvailable);
  }
  async function refresh(){if(busy)return;const epoch=metricsEpoch;try{
    const result=await metrics.request(()=>call('pickerstatus'),()=>epoch===metricsEpoch&&!document.hidden);if(result===null)return;
    data=result;reconcile(result);
    const p=pending;
    if(p&&p.cmd!=='pickerapply'&&!pendingStartCurrent(p)){pending=null;$('confirmation').hidden=true;draftPlan=null;actionError='selection_changed';}
    else if(p&&p.cmd!=='pickerapply'&&p.planPost){
      const plan=await call('pickerplan',p.planPost);
      if(pending===p&&(!validPoolPlan(plan,p.selection)||plan.plan_sha256!==p.extra.plan_sha256)){
        pending=null;$('confirmation').hidden=true;draftPlan=null;actionError='plan_changed';
      }
    }
    render();
  }catch(e){if(pending&&pending.cmd!=='pickerapply'){pending=null;$('confirmation').hidden=true;draftPlan=null;}
    text('error',e.name==='AbortError'?(language==='ru'?'Статус не получен вовремя. Работа на роутере может продолжаться; повторите обновление.':'Status request timed out. Work on the router may continue; refresh again.'):t(e.message));}}
  const poller=new PickerStatusPoller(document,refresh,renderMetrics,()=>{metricsEpoch++;metrics.pause();});
  async function action(cmd,extra){
    const newWindow=Boolean(extra.request_id&&ownedWindow?.request_id!==extra.request_id);
    if(newWindow){
      forgetWindow();
      ownedWindow={request_id:extra.request_id,window_id:randomId()};
      windowTimer=setInterval(()=>reportWindow('open'),20000);
    }
    const windowId=extra.request_id?ownedWindow.window_id:null;
    metricsEpoch++;busy=true;actionError='';rememberMutation({cmd,extra:{...extra}});render();
    try{
      data=await call(cmd,windowId?{...extra,window_id:windowId}:extra);
      observeWindow(data);
      if(windowId===ownedWindow?.window_id)reportWindow('open');
      rememberMutation(null);
    }
    catch(e){
      if(e.confirmed){
        if(newWindow&&windowId===ownedWindow?.window_id)forgetWindow();
        rememberMutation(null);actionError=e.message;
      }
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
  for(const id of ['goal-main','goal-all','goal-selected','goal-youtube','goal-discord','goal-instagram','goal-torrents','search','custom-enabled','custom-only','custom-joint'])$(id).addEventListener('change',draftChanged);
  $('result-show-totals').addEventListener('change',render);
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
    const goal=only||$('goal-all').checked?'all':$('goal-main').checked?mainGoal:services.filter(s=>$('goal-'+s).checked).join(',');
    if(!goal){actionError='choose_goal';render();return;}
    const requested=requestedPool();if(requested===null){actionError='invalid_pool';render();return;}
    const rounds=$('search').value==='synthesis'?$('rounds-value').value:'1';
    if(roundChoice(rounds)===null||$('search').value==='synthesis'&&roundChoice(rounds)<2){actionError='invalid_rounds';render();return;}
    if(custom&&data.custom_capability?.available!==true){actionError=data.custom_capability?.code||'unsupported_runtime';render();return;}
    const snapshot=draftKey(),extra={request_id:randomId(),consent:'test',goal};
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
      selectionDescription(goal,$('search').value,language,selected)+' '+poolDescription(draftPlan.plan.concurrency_choice,language)+' '+(language==='ru'?`Прогонов подряд: ${rounds}. Начать подбор? Роутер будет временно менять стратегию. При необходимости сначала сохраните предыдущий отчёт.`:`${rounds} sequential run(s). Start the search? The router will switch strategies temporarily. Save the previous report first if you need it.`));
  });
  $('cancel').addEventListener('click',()=>void action('pickercancel',{id:data.job.id}));
  $('refresh').addEventListener('click',()=>{savedCards.clear();void poller.refresh();});
  function downloadJson(raw,filename){
    const a=document.createElement('a');
    const url=URL.createObjectURL(new Blob([raw],{type:'application/json'}));
    a.href=url;a.download=filename;a.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  $('custom-check').addEventListener('click',async()=>{
    if(busy||data?.active)return;const input=$('custom-sites').value;busy=true;actionError='';customErrors=[];render();
    try{const preview=await call('pickertargets',{custom_sites:input});
      if(!pageActive||$('custom-sites').value!==input)return;
      if(!validTargetPreview(preview)){customErrors=preview.errors||[{line:0,code:'invalid_hostname'}];return;}
      sessionStorage.setItem('nfqws-site-check-targets-v1',JSON.stringify(preview.hosts));
      window.location.assign(panelBase+'?site-check=1');
    }catch(e){actionError=e.message;}finally{busy=false;render();}
  });
  function shareDownload(raw,filename){
    const bytes=new TextEncoder().encode(raw);if(bytes.length<1||bytes.length>1048576)throw new Error('output_limit');
    sessionStorage.setItem('nfqws-share-download-v1',JSON.stringify({filename,media_type:'application/json',data_base64:btoa(Array.from(bytes,c=>String.fromCharCode(c)).join(''))}));
    window.location.assign(panelBase+'?share-frank=1');
  }
  $('share-report').addEventListener('click',()=>{if(!data||data.active||!jobView(data.job,language).reportAvailable)return;
    try{shareDownload(JSON.stringify(data,null,2),'nfqws2-strategy-selection.json');}catch(e){actionError=e.message;render();}});
  $('download').addEventListener('click',()=>{if(!data||data.active===true||!jobView(data.job,language).reportAvailable)return;downloadJson(JSON.stringify(data,null,2),'nfqws2-strategy-selection.json');});
  const labels={ru:{title:'Подбор стратегии',intro:'Роутер проверит варианты и вернёт исходные настройки. Вы сами решите, применять ли найденную стратегию.','device-title':'Состояние роутера','start-title':'Настройки подбора','goal-title':'Какие сервисы важны','goal-all-label':'Все сервисы','goal-selected-label':'Выбранные сервисы','goal-help':'Выбранные сервисы влияют на итог. Роутер проверит и другие сайты, чтобы заметить ухудшения.',warning:'Во время проверки интернет может ненадолго прерваться. Если закрыть вкладку или уйти со страницы, роутер остановит подбор и начнёт возвращать исходные настройки. При потере связи это может занять несколько минут. Чтобы проверить результат, снова откройте подбор.','extended-label':'Проверить ещё варианты, если готовые стратегии не помогут','extended-help':'Роутер попробует дополнительные настройки соединения. Правила для отдельных сервисов и игр сохранятся.','results-title':'Сравнение',explanation:'Каждую стратегию проверили дважды. В таблице показано, сколько проверок прошло успешно. Проверка DNS не влияет на сравнение.',note:'После применения проверьте видео, голосовые звонки и другие нужные функции в самих приложениях. Роутер измеряет только доступность сайтов.','confirm-submit':'Продолжить','confirm-dismiss':'Отмена'},en:{title:'Strategy search',intro:'The router tests strategies and restores your previous settings. You decide whether to apply the suggested strategy.','device-title':'Router status','start-title':'Search settings','goal-title':'Which services matter','goal-all-label':'All services','goal-selected-label':'Selected services','goal-help':'Selected services have priority in the results. The router also checks other sites to spot any decline.',warning:'Your connection may briefly drop during testing. Closing the tab or leaving this page stops the search and starts restoring your previous settings. If the connection drops, this can take a few minutes. Reopen the search to check the result.','extended-label':'Try more options if the ready-made strategies do not help','extended-help':'The router tries more connection settings and keeps your rules for individual services and games.','results-title':'Comparison',explanation:'Each strategy was measured twice. The table shows how many checks passed. DNS is checked separately and has no effect on the comparison.',note:'After applying, check playback, calls, and other features you need in the apps themselves. The router only checks whether sites are reachable.','confirm-submit':'Continue','confirm-dismiss':'Cancel'}};
  Object.assign(labels.ru,{'search-label':'Что проверить','search-synthesis':'Создать новую стратегию','search-profiles':'Сравнить готовые стратегии','search-help':'Создание новой стратегии пока в бета-версии. Роутер пробует разные настройки и повторно проверяет лучшие варианты. Улучшение не гарантируется. Проверки идут по IPv4.',explanation:'Роутер повторно проверяет лучшие варианты и сравнивает итог с вашей исходной стратегией и соединением без обхода.'});
  Object.assign(labels.en,{'search-label':'What to test','search-synthesis':'Create a new strategy','search-profiles':'Compare existing strategies','search-help':'Creating new strategies is in beta. The router tries different settings and checks the most promising options again. Results may vary. Tests use IPv4.',explanation:'The router checks promising strategies again and compares the result with your original strategy and a connection without bypass.'});
  Object.assign(labels.ru,{'rounds-title':'Количество прогонов','rounds-label':'Прогонов подряд: от 2 до 10','rounds-help':'Следующий прогон начнётся после восстановления настроек и проверки соединения. При остановке или ошибке вся серия завершается.'});
  Object.assign(labels.en,{'rounds-title':'Number of runs','rounds-label':'Consecutive runs: 2 to 10','rounds-help':'Each run starts after the router restores its settings and checks that it is ready. Stopping the search or encountering an error ends the series.'});
  Object.assign(labels.ru,{'goal-torrents-label':'Торрент-трекеры','torrent-goal-help':'Торрент-трекеры в проверке — NNMClub, RuTracker, Rutor и tapochek.net.'});
  Object.assign(labels.en,{'goal-torrents-label':'Torrent trackers','torrent-goal-help':'The tracker test covers NNMClub, RuTracker, Rutor and tapochek.net.'});
  words.ru.torrent_sites_incompatible='Дополнение неприменимо к этому варианту HTTPS';words.en.torrent_sites_incompatible='This HTTPS variant cannot use the tracker extension';
  Object.assign(labels.ru,{'search-synthesis':'Создать новую стратегию','custom-title':'Свои сайты','custom-enabled-label':'Добавить свои сайты к подбору','custom-sites-label':'До десяти сайтов или публичных IPv4-адресов','custom-joint-label':'Подбирать для своих сайтов и выбранных сервисов','custom-only-label':'Подбирать только для своих сайтов','share-report':'Поделиться с Фрэнком','custom-check':'Проверить, открываются ли сайты','custom-examples':'Один адрес на строку. Подойдут example.com, https://example.org и 8.8.8.8.','custom-help':'Роутер проверит главную страницу каждого сайта по HTTPS (TLS 1.2 и 1.3). Для IP-адреса нужен сертификат, выданный на этот адрес. Правило для IP может затронуть другие сайты на нём. Сбой защищённого соединения (TLS) может иметь разные причины. Telegram исключён.'});
  Object.assign(labels.en,{'search-synthesis':'Create a new strategy','custom-title':'Custom sites','custom-enabled-label':'Add your own sites to the search','custom-sites-label':'Up to ten sites or public IPv4 addresses','custom-joint-label':'Search for my sites and the selected services','custom-only-label':'Search for my sites only','share-report':'Share with Frank','custom-check':'Check whether sites open','custom-examples':'Enter one address per line, such as example.com, https://example.org or 8.8.8.8.','custom-help':'The router checks the home page of each site over HTTPS (TLS 1.2 and 1.3). An IP address needs a certificate issued for that address, and an IP rule can affect other sites there. A secure connection (TLS) can fail for several reasons. Telegram is excluded.'});
  Object.assign(labels.ru,{'pool-title':'Одновременные проверки','pool-value-label':'Число проверок','pool-help':'Обычно достаточно 10–100. Большие значения не гарантируют ускорения подбора.'});
  Object.assign(labels.en,{'pool-title':'Simultaneous checks','pool-value-label':'Number of checks','pool-help':'Usually 10–100 is enough. A higher number may give no speed gain.'});
  Object.assign(labels.ru,{'goal-main-label':'Основные сервисы — YouTube, Discord и Instagram','result-columns-label':'Колонки результатов','result-columns-auto':'Авто','result-show-totals-label':'Показать общие показатели'});
  Object.assign(labels.en,{'goal-main-label':'Main services — YouTube, Discord and Instagram','result-columns-label':'Result columns','result-columns-auto':'Auto','result-show-totals-label':'Show overall results'});
  Object.assign(labels.ru,{'round-help-title':'Как работают прогоны',
    'round-help-first':'В первом прогоне роутер замеряет исходную стратегию и, если доступно для выбранной цели, сток. Затем он проверяет варианты до указанного лимита и повторно измеряет перспективные.',
    'round-help-next':'Во втором и следующих прогонах генератор использует результаты предыдущих. Он развивает удачные находки и пробует другие сочетания. Уже проверенные сочетания пропускаются, пока они есть в памяти. При сравнении со стоком удачную стратегию предыдущего прогона проверяют отдельно ещё дважды.'});
  Object.assign(labels.en,{'round-help-title':'How runs work',
    'round-help-first':'The first run measures your original strategy and stock, when stock is available for the selected goal. It tests variants up to the stated limit and measures promising ones again.',
    'round-help-next':'The second and later runs use previous results to refine promising variants and try other combinations. Previously checked combinations are skipped while they remain in memory. When comparing with stock, the previous successful strategy is measured twice again.'});
  $('language').addEventListener('click',()=>{language=language==='ru'?'en':'ru';document.documentElement.lang=language;$('language').textContent=language==='ru'?'EN':'RU';for(const [id,value]of Object.entries(labels[language]))text(id,value);showResultColumnCount();render();});
  let authenticated=false;
  document.addEventListener('visibilitychange',()=>{if(pageActive)reportWindow('open');});
  window.addEventListener('pagehide',()=>{
    pageActive=false;
    if(ownedWindow){
      reportWindow('closed');
      if(outstanding?.extra.request_id===ownedWindow.request_id)rememberMutation(null);
      forgetWindow();
    }
    pending=null;savedCards.clear();$('confirmation').hidden=true;poller.stop();
  });
  window.addEventListener('pageshow',()=>{pageActive=true;if(authenticated)poller.start();});
  void (async()=>{try{const s=await call('status');csrf=s.csrf_token;authenticated=true;poller.start();}catch(e){text('error',t(e.message));}})();
}
