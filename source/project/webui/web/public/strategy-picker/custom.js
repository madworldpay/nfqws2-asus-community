// Presentation of committed root-HTTPS samples. Native Rustls/QUIC metrics
// remain separate; only the backend can authorize Apply or export.
export function publicIpv4(host){
  if(typeof host!=='string'||!/^\d+\.\d+\.\d+\.\d+$/.test(host))return false;
  const octets=host.split('.').map(Number);
  if(octets.some(v=>!Number.isInteger(v)||v>255)||octets.join('.')!==host)return false;
  const [a,b,c]=octets;
  return !(a===0||a===10||a===127||a>=224||a===100&&b>=64&&b<=127||a===169&&b===254||
    a===172&&b>=16&&b<=31||a===192&&(b===0&&(c===0||c===2)||b===31&&c===196||b===52&&c===193||
      b===88&&c===99||b===168||b===175&&c===48)||a===198&&(b===18||b===19||b===51&&c===100)||a===203&&b===0&&c===113);
}
function hostsValid(hosts){
  return Array.isArray(hosts)&&hosts.length>=1&&hosts.length<=10&&new Set(hosts).size===hosts.length&&
    hosts.every(h=>publicIpv4(h)||typeof h==='string'&&h.length<=253&&/^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{1,62}$/.test(h)&&
      !['local','localhost','localdomain','lan','home','corp','internal','invalid','test','example','onion','arpa',
        't.me','telegram.org','telegram.me','telesco.pe'].some(e=>h===e||h.endsWith('.'+e)));
}
const hex=(v,n)=>typeof v==='string'&&new RegExp('^[a-f0-9]{'+n+'}$').test(v);
export function customTargetIdentity(hosts){
  return hostsValid(hosts)?hosts.map(host=>({kind:publicIpv4(host)?'ipv4':'domain',host})):null;
}
export function validTargetPreview(preview){
  const targets=customTargetIdentity(preview?.hosts);
  if(preview?.valid!==true||targets===null)return false;
  if(!targets.some(t=>t.kind==='ipv4'))return preview.schema_version===undefined&&preview.target_policy_version===undefined&&preview.targets===undefined;
  return preview.schema_version===2&&preview.target_policy_version==='custom-public-targets-v2'&&hex(preview.sha256,64)&&
    JSON.stringify(preview.targets)===JSON.stringify(targets);
}
export function customMeasurements(runs){
  if(!Array.isArray(runs)||![1,2].includes(runs.length)||!hostsValid(runs[0]?.hosts))return null;
  const first=runs[0],hosts=first.hosts,ids=new Set(),typed=customTargetIdentity(hosts),mixed=typed.some(t=>t.kind==='ipv4');
  for(const run of runs){
    if(!run||!hex(run.sample_id,32)||ids.has(run.sample_id)||!hex(run.targets,64)||!hex(run.context_sha256,64)||
      run.targets!==first.targets||run.context_sha256!==first.context_sha256||JSON.stringify(run.hosts)!==JSON.stringify(hosts)||
      !Array.isArray(run.cells)||run.cells.length!==hosts.length*2)return null;
    if(mixed){
      if(run.schema_version!==2||run.fingerprint!=='custom-pinned-root-score-v2'||
        run.probe_fingerprint!=='php-openssl-pinned-public-targets-v2'||run.target_policy_version!=='custom-public-targets-v2'||
        JSON.stringify(run.target_identities)!==JSON.stringify(typed)||
        !hex(run.dns_context,64)||!hex(run.manifest_sha256,64)||!hex(run.sample_sha256,64)||
        run.dns_context!==first.dns_context||run.manifest_sha256!==first.manifest_sha256)return null;
    }else if(run.schema_version!==1||run.target_policy_version!==undefined||run.target_identities!==undefined)return null;
    ids.add(run.sample_id);
    for(let i=0;i<run.cells.length;i++){
      const c=run.cells[i];
      if(!c||c.host!==hosts[Math.floor(i/2)]||c.tls!==(i%2?'tls13':'tls12')||
        !['response','read_limited','timeout','tls_error','connection_error','unavailable','blocked_address'].includes(c.outcome)||
        c.http_status!==null&&(!Number.isSafeInteger(c.http_status)||c.http_status<200||c.http_status>599))return null;
      const responded=['response','read_limited'].includes(c.outcome);
      if(responded&&c.http_status===null||c.responded!==responded||c.root_ok!==(responded&&c.http_status>=200&&c.http_status<300))return null;
    }
  }
  let stable=0,responded=0;
  const rows=hosts.map((host,i)=>{
    const row={host};
    for(const [offset,tls]of [[0,'tls12'],[1,'tls13']]){
      const cells=runs.map(r=>r.cells[i*2+offset]),values=cells.map(c=>c.root_ok?1:0);
      const low=Math.min(...values);stable+=low;if(cells.every(c=>c.responded))responded++;
      row[tls]={low,high:Math.max(...values)};
    }return row;
  });
  return {repeats:runs.length,total:hosts.length*2,stable,responded,rows};
}
export function customComparison(job){
  if(job?.state!=='completed'||job.restored!==true||job.can_export!==true||job.generation?.verified!==true||
    !hostsValid(job.custom_hosts)||!Array.isArray(job.profiles))return null;
  const before=job.profiles.filter(p=>p?.rank?.reason==='baseline');
  const after=job.profiles.filter(p=>p?.id+':'+(p?.recipe??'')===job.generated);
  if(before.length!==1||after.length!==1||[before[0],after[0]].some(p=>p.sample_type!=='repeated'))return null;
  const a=customMeasurements(before[0].custom_runs),b=customMeasurements(after[0].custom_runs);
  if(!a||!b||a.repeats!==2||b.repeats!==2||a.total!==b.total||
    before[0].custom_runs[0].targets!==after[0].custom_runs[0].targets||
    before[0].custom_runs[0].context_sha256!==after[0].custom_runs[0].context_sha256||
    JSON.stringify(a.rows.map(r=>r.host))!==JSON.stringify(job.custom_hosts)||
    JSON.stringify(b.rows.map(r=>r.host))!==JSON.stringify(job.custom_hosts))return null;
  if(a.rows.some((r,i)=>['tls12','tls13'].some(tls=>b.rows[i][tls].low<r[tls].low)))return null;
  return {before:a.stable,after:b.stable,total:a.total,repeats:2};
}
export function customScope(hosts,only,goal='all',language='ru'){
  if(!hostsValid(hosts)||typeof only!=='boolean')return null;
  const names={youtube:'YouTube',discord:'Discord',instagram:'Instagram',torrents:language==='ru'?'Торрент-трекеры':'Torrent trackers'};
  const native=goal==='all'?(language==='ru'?'все встроенные сервисы':'all built-in services'):String(goal).split(',').map(g=>names[g]||g).join(' + ');
  const scope=(language==='ru'?'Свои сайты: ':'Custom sites: ')+hosts.join(', ');
  const selected=only?scope+(language==='ru'?'. Встроенные проверки — контроль без ухудшений.':'. Built-in checks are nonregression controls.'):
    scope+(language==='ru'?'. Совместная цель: ':'. Joint goal: ')+native+'.';
  return selected+(hosts.some(publicIpv4)?(language==='ru'?
    ' Правило IP действует на весь HTTPS-трафик к этому адресу и может затрагивать другие HTTPS-сайты на нём. Ошибка TLS сама по себе не доказывает блокировку.':
    ' An IP rule covers HTTPS traffic to that address and can affect other HTTPS sites on it. A TLS failure alone does not establish blocking.'):'');
}
export function targetErrors(errors,language='ru'){
  const ru={empty:'Введите хотя бы один сайт.',input_too_long:'Не более 4096 байт текста.',too_many_lines:'Слишком много строк.',
    too_many_hosts:'Можно указать до десяти доменов и публичных IPv4 суммарно.',invalid_hostname:'Недопустимый домен или IPv4.',unsupported_scheme:'Допустимы адреса HTTP и HTTPS.',
    non_public_ipv4:'Нужен публичный IPv4; локальные и зарезервированные адреса запрещены.',cidr_not_allowed:'Укажите один IPv4 без маски CIDR.',
    credentials_not_allowed:'Адрес не должен содержать логин или пароль.',port_not_allowed:'Не указывайте порт.',telegram_excluded:'Telegram исключён из генерации.'};
  const en={empty:'Enter at least one site.',input_too_long:'Use at most 4096 bytes of text.',too_many_lines:'Too many lines.',
    too_many_hosts:'Enter up to ten domains and public IPv4 addresses combined.',invalid_hostname:'Invalid domain or IPv4 address.',unsupported_scheme:'Use an HTTP or HTTPS address.',
    non_public_ipv4:'Use a public IPv4 address; local and reserved addresses are excluded.',cidr_not_allowed:'Enter one IPv4 address without a CIDR prefix.',
    credentials_not_allowed:'Do not include a username or password.',port_not_allowed:'Do not specify a port.',telegram_excluded:'Telegram is excluded from generation.'};
  const words=language==='ru'?ru:en;
  return (Array.isArray(errors)?errors.slice(0,33):[{line:0,code:'invalid_hostname'}]).map(e=>
    (Number.isSafeInteger(e?.line)&&e.line>0?(language==='ru'?'Строка ':'Line ')+e.line+': ':'')+(words[e?.code]||words.invalid_hostname)).join('\n');
}
