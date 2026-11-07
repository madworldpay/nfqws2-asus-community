(() => {
  'use strict';

  const endpoint = new URL('../index.php', location.href);
  const $ = (id) => document.getElementById(id);
  const state = {
    draft: { schema_version: 1, mode: 'common', devices: [], profiles: [] },
    saved: '', revision: null, discovery: null, loaded: false,
    busy: false, stale: false, version: 0, previewVersion: null, dragId: null,
    runtime: null, runtimeKnown: false, startInitialized: false, pollTimer: null, catalog: [],
  };
  let strategyNames = { current: 'Текущая стратегия', stock: 'Стоковая стратегия' };
  let requestChain = Promise.resolve();
  const errors = {
    unauthorized: 'Сеанс панели истёк. Откройте основную панель и войдите, затем повторите действие. Правки остаются здесь.',
    forbidden: 'Панель не разрешила запрос. Откройте основную панель, проверьте вход и повторите действие. Правки остаются здесь.',
    invalid_request: 'Панель отклонила запрос. Проверьте поля черновика.',
    invalid_draft: 'Черновик не прошёл проверку. Проверьте названия, адреса и выбранные устройства.',
    stale_revision: 'Сохранённый черновик изменился в другой вкладке. Ваши правки не заменены и не сохранены поверх него.',
    storage_unavailable: 'Хранилище черновика сейчас недоступно. Ваши правки остаются на странице; повторите сохранение позже.',
    busy: 'Черновик занят другим запросом. Подождите и повторите действие.',
    invalid_response: 'Панель вернула неожиданный ответ. Проверьте вход в основную панель и повторите действие.',
    network: 'Нет ответа от панели. Проверьте соединение и повторите действие. Ваши правки остаются на странице.',
    timeout: 'Панель не ответила вовремя. Повторите действие; ваши правки остаются на странице.',
    runtime_unavailable: 'Для применения нужна актуальная экспериментальная установка на этом роутере. Черновик и библиотека сохранены.',
    runtime_profile_limit: 'Одновременно можно использовать до четырёх отличающихся стратегий помимо общей.',
    runtime_limit: 'Профиль превышает ограничения экспериментальной версии. Уменьшите количество ресурсов или устройств.',
    library_limit: 'В библиотеке уже восемь сохранённых стратегий.',
    unresolved_profile_resource: 'Стратегия ссылается на отсутствующий или недоступный ресурс. Проверьте зависимости в обычном импорте.',
    profile_import_incomplete: 'В экспорте не удалось подтвердить все зависимости стратегии. Проверьте его в обычном импорте.',
    lua_trust: 'Чтобы добавить профиль с Lua, подтвердите доверие к его коду галочкой в библиотеке.',
    source_changed: 'Рабочая конфигурация изменилась во время подготовки. Обновите состояние и повторите действие.',
    strategy_unavailable: 'Выбранная стратегия отсутствует в библиотеке. Выберите доступный вариант.',
  };

  function element(tag, className, content) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (content !== undefined) node.textContent = content;
    return node;
  }
  function button(label, handler, className = '') {
    const node = element('button', className, label);
    node.type = 'button';
    node.addEventListener('click', handler);
    return node;
  }
  function problem(code) { return Object.assign(new Error(code), { code }); }
  function clone(value) { return JSON.parse(JSON.stringify(value)); }
  function serialized() { return JSON.stringify(state.draft); }
  function dirty() { return state.loaded && serialized() !== state.saved; }
  function randomId(prefix) {
    const bytes = crypto.getRandomValues(new Uint8Array(4));
    return prefix + Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
  }
  function notice(message = '', type = '') {
    $('notice').textContent = message;
    $('notice').className = 'notice' + (type ? ' ' + type : '');
    $('notice').hidden = !message;
  }
  function report(error) {
    if (error.code === 'stale_revision') state.stale = true;
    notice(error.userMessage || errors[error.code] || errors.network, 'error');
    sync();
  }
  function sync() {
    const pending = jobPending();
    $('editor').disabled = state.busy || pending || !state.loaded;
    $('reload').disabled = state.busy;
    $('preview').disabled = state.busy || !state.loaded;
    $('save').disabled = state.busy || pending || !state.loaded || !dirty() || state.stale;
    $('refresh').disabled = state.busy || !state.loaded;
    $('add-profile').disabled = state.busy || state.draft.profiles.length >= 16;
    $('stale-notice').hidden = !state.stale;
    $('apply').disabled = !!state.busy || pending || !state.loaded || dirty() || state.stale || !state.runtime?.available;
    $('start-after').disabled = !!state.busy || pending || !state.runtime?.available;
    for (const id of ['capture-current', 'library-import', 'catalog-load']) $(id).disabled = !!state.busy || pending || !state.loaded || !state.runtime?.available;
    $('catalog-add').disabled = !!state.busy || pending || !$('catalog-profile').value || !state.runtime?.available;
    $('runtime-refresh').disabled = !!state.busy || !state.runtimeKnown;
    if (state.busy) {
      $('save-state').textContent = state.busy;
      $('save-hint').textContent = 'Дождитесь ответа панели.';
    } else if (!state.loaded) {
      $('save-state').textContent = 'Черновик не загружен';
      $('save-hint').textContent = 'Используйте «Загрузить сохранённый», чтобы повторить.';
    } else {
      $('save-state').textContent = dirty() ? 'Есть несохранённые изменения' : 'Черновик сохранён';
      $('save-hint').textContent = state.stale ? 'Обнаружена другая версия черновика.' : 'Рабочая стратегия не изменяется.';
    }
    renderRuntime();
    if (state.previewVersion !== null) {
      $('preview-caption').textContent = state.previewVersion !== state.version
        ? 'Черновик изменён после предпросмотра. Обновите предпросмотр. Правила не применены.'
        : 'Результат проверки черновика. Правила не применены.';
    }
  }
  function changed() { state.version += 1; sync(); }
  function userError(message) { return Object.assign(new Error(message), { userMessage: message }); }

  async function post(cmd, params = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(endpoint, {
        method: 'POST', credentials: 'same-origin', redirect: 'error', cache: 'no-store',
        body: new URLSearchParams({ cmd, ...params }), signal: controller.signal,
      });
      if (response.status === 401) throw problem('unauthorized');
      if (response.status === 403) throw problem('forbidden');
      if (!/^application\/json(?:;|$)/i.test(response.headers.get('Content-Type') || '')) throw problem('invalid_response');
      const text = await response.text();
      if (text.length > (cmd === 'importcatalogload' ? 6291456 : 1048576)) throw problem('invalid_response');
      let result;
      try { result = JSON.parse(text); } catch { throw problem('invalid_response'); }
      if (!result || typeof result !== 'object') throw problem('invalid_response');
      if (typeof result.error === 'string') throw problem(result.error);
      if (!response.ok) throw problem('invalid_response');
      return result;
    } catch (error) {
      if (error.name === 'AbortError') throw problem('timeout');
      throw error;
    } finally { clearTimeout(timeout); }
  }
  async function request(cmd, params = {}) {
    const run = async () => {
      const status = await post('status');
      if (typeof status.csrf_token !== 'string' || !status.csrf_token) throw problem('unauthorized');
      return post(cmd, { csrf_token: status.csrf_token, ...params });
    };
    const pending = requestChain.then(run, run);
    requestChain = pending.catch(() => {});
    return pending;
  }
  function checkedStatus(data) {
    const draft = data.draft;
    if (data.schema_version !== 1 || !/^[a-f0-9]{64}$/.test(data.revision || '') ||
        !draft || draft.schema_version !== 1 || !['common', 'split'].includes(draft.mode) ||
        !Array.isArray(draft.devices) || !Array.isArray(draft.profiles) ||
        draft.devices.length > 128 || draft.profiles.length > 16 ||
        draft.devices.some((d) => !d || typeof d.id !== 'string' || typeof d.name !== 'string' || typeof d.mac !== 'string' || !Array.isArray(d.addresses) || d.addresses.some((a) => typeof a !== 'string')) ||
        draft.profiles.some((p) => !p || typeof p.id !== 'string' || typeof p.name !== 'string' || typeof p.enabled !== 'boolean' || !/^(?:current|stock|saved-[a-f0-9]{16})$/.test(p.strategy) || !Array.isArray(p.device_ids)) ||
        !data.discovery || !['available', 'partial', 'unavailable'].includes(data.discovery.state) || !Array.isArray(data.discovery.devices) ||
        data.discovery.devices.some((d) => !d || typeof d.id !== 'string' || typeof d.name !== 'string' || typeof d.mac !== 'string' || !Array.isArray(d.addresses) || !Array.isArray(d.sources))) {
      throw problem('invalid_response');
    }
    return data;
  }
  function acceptTemplates(rows = []) {
    if (!Array.isArray(rows) || rows.length > 10 || rows.some((r) => !r || !/^(?:current|stock|saved-[a-f0-9]{16})$/.test(r.id) || typeof r.name !== 'string' || r.name.length > 256)) throw problem('invalid_response');
    strategyNames = { current: 'Текущая стратегия', stock: 'Стоковая стратегия' };
    rows.forEach((r) => { strategyNames[r.id] = r.name; });
    $('library-count').textContent = `В библиотеке: ${rows.filter((r) => r.id.startsWith('saved-')).length} / 8. Одновременно — до четырёх отличающихся стратегий помимо общей.`;
  }
  function acceptRuntime(data) {
    if (!data || typeof data.available !== 'boolean' || typeof data.running !== 'boolean' || !['common', 'split'].includes(data.mode) ||
      (data.job !== null && (!data.job || !/^[a-f0-9]{32}$/.test(data.job.id) || !['queued', 'running', 'succeeded', 'failed'].includes(data.job.state) || typeof data.job.phase !== 'string'))) throw problem('invalid_response');
    state.runtime = data; state.runtimeKnown = true;
    if (!state.startInitialized) { $('start-after').checked = data.running; state.startInitialized = true; }
  }
  function jobPending() { return ['queued', 'running'].includes(state.runtime?.job?.state); }
  const phaseNames = { queued: 'Ожидание запуска', validating: 'Проверка стратегий и правил', stopping: 'Остановка службы', applying: 'Сохранение рабочего режима', starting: 'Запуск службы', checking: 'Проверка процессов и очередей', restoring: 'Восстановление прежнего режима', finished: 'Завершено' };
  const causeNames = { queue_conflict: 'Очередь занята другим процессом.', invalid_profile_engine: 'NFQWS2 отклонил параметры или ресурсы стратегии.', profile_validation_failed: 'Не прошла проверка параметров или правил захвата.', profile_start_failed: 'Не удалось подтвердить запуск всех экземпляров службы.', profile_stop_failed: 'Не удалось подтвердить остановку службы.', queue_unavailable: 'Не подтверждена привязка очереди.', worker_interrupted: 'Рабочий процесс был прерван.', worker_start_failed: 'Рабочий процесс не запустился.', recovery_required: 'Автоматическое восстановление не подтверждено.', package_operation_active: 'Выполняется обновление основного пакета.' };
  function failureText() {
    const job = state.runtime?.job;
    if (!job || job.state !== 'failed') return '';
    return `Этап: ${phaseNames[job.phase] || job.phase}\nПричина: ${causeNames[job.code] || errors[job.code] || job.code || 'Неизвестная ошибка'}\nКод: ${job.code || 'unknown'}\nИсходный код: ${job.original_code || job.code || 'unknown'}\n${job.recovered === true ? 'Восстановлен прежний режим и состояние службы.' : job.recovered === false ? 'Восстановление не подтверждено.' : 'Изменение рабочего режима не подтверждено.'}\nОперация: ${job.id}`;
  }
  function renderRuntime() {
    const data = state.runtime; const job = data?.job;
    if (!data || !data.available) $('runtime-info').textContent = 'Применение недоступно: требуется актуальная экспериментальная установка. Черновик можно редактировать и сохранять.';
    else if (jobPending()) $('runtime-info').textContent = phaseNames[job.phase] || 'Применение выполняется…';
    else {
      const prefix = job?.state === 'succeeded' ? 'Применено: ' : 'Рабочий режим: ';
      $('runtime-info').textContent = prefix + (data.mode === 'split' ? 'по устройствам.' : 'общий.') + (data.running ? ' Служба включена.' : data.core_running ? ' Готовность отдельных очередей не подтверждена.' : ' Служба выключена.');
    }
    $('runtime-progress').hidden = !jobPending();
    $('runtime-progress').value = ({ queued: 0, validating: 10, stopping: 35, applying: 55, starting: 70, checking: 90, restoring: 45, finished: 100 })[job?.phase] || 0;
    const details = failureText(); $('job-details').textContent = details; $('job-details').hidden = !details; $('copy-error').hidden = !details;
  }
  function schedulePoll() {
    clearTimeout(state.pollTimer);
    if (!state.runtimeKnown || document.hidden) return;
    state.pollTimer = setTimeout(async () => {
      if (state.busy) { schedulePoll(); return; }
      try { acceptRuntime(await request('deviceprofilesruntime')); sync(); }
      catch (error) { report(error); }
      finally { schedulePoll(); }
    }, jobPending() ? 1200 : 15000);
  }
  async function refreshLibrary() {
    const data = checkedStatus(await request('deviceprofilesstatus'));
    acceptTemplates(data.templates); if (data.runtime) acceptRuntime(data.runtime);
    if (data.revision !== state.revision) state.stale = true;
    renderProfiles(); sync(); schedulePoll();
  }
  async function activate() {
    if (dirty() || state.stale || jobPending() || !state.runtime?.available) return;
    await perform('Подготовка применения…', async () => {
      const bytes = crypto.getRandomValues(new Uint8Array(16));
      const request_id = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
      const job = await request('deviceprofilesapply', { revision: state.revision, request_id, consent: 'apply', start_after: $('start-after').checked ? '1' : '0' });
      acceptRuntime({ ...state.runtime, job }); schedulePoll();
      notice('Применение запущено. Операция продолжится после закрытия вкладки.');
    });
  }
  async function captureCurrent() {
    const name = $('strategy-name').value.trim();
    if (!name) { notice('Укажите название стратегии.', 'error'); return; }
    await perform('Сохранение стратегии…', async () => {
      await request('deviceprofilescapture', { name }); await refreshLibrary();
      notice('Текущая стратегия добавлена в библиотеку. Теперь её можно выбрать в профиле.');
    });
  }
  async function importDocument(document, name) {
    if (typeof document !== 'string' || new TextEncoder().encode(document).length > 4194304) throw userError('JSON-экспорт превышает 4 МБ.');
    await request('deviceprofilesimport', { name: name.slice(0, 64), document, trusted_lua: $('trust-lua').checked ? '1' : '0' });
    await refreshLibrary(); notice('Стратегия добавлена в библиотеку. Выберите её в нужном профиле.');
  }
  async function importFile() {
    const file = $('strategy-file').files?.[0];
    if (!file) { notice('Выберите единый JSON-экспорт стратегии.', 'error'); return; }
    await perform('Чтение JSON-экспорта…', async () => {
      if (file.size > 4194304) throw userError('JSON-экспорт превышает 4 МБ.');
      await importDocument(await file.text(), $('strategy-name').value.trim() || file.name.replace(/\.json$/i, ''));
    });
  }
  async function loadCatalog() {
    await perform('Загрузка каталога…', async () => {
      const data = await request('importcatalog');
      if (!Array.isArray(data.profiles) || data.profiles.length > 128 || data.profiles.some((p) => !p || !/^[a-z0-9][a-z0-9-]{0,63}$/.test(p.id) || !/^[a-f0-9]{64}$/.test(p.sha256) || typeof p.title !== 'string' || typeof p.description !== 'string')) throw problem('invalid_response');
      state.catalog = data.profiles;
      $('catalog-profile').replaceChildren(element('option', '', 'Выберите профиль'));
      $('catalog-profile').options[0].value = '';
      state.catalog.forEach((profile) => { const option = element('option', '', profile.title); option.value = profile.id; $('catalog-profile').append(option); });
      $('catalog-controls').hidden = false; $('catalog-description').textContent = '';
      notice('Каталог загружен. Выберите профиль и проверьте его описание.');
    });
  }
  async function addCatalog() {
    const selected = state.catalog.find((p) => p.id === $('catalog-profile').value); if (!selected) return;
    await perform('Загрузка выбранной стратегии…', async () => {
      const result = await request('importcatalogload', { id: selected.id, sha256: selected.sha256 });
      await importDocument(result.document, selected.title);
    });
  }
  async function copyFailure() {
    const text = failureText(); if (!text) return;
    try {
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(text);
      else {
        const field = document.createElement('textarea'); field.value = text; field.readOnly = true; field.style.position = 'fixed'; field.style.opacity = '0';
        document.body.append(field); field.select(); const copied = document.execCommand('copy'); field.remove(); if (!copied) throw problem('copy_failed');
      }
      notice('Причина отказа скопирована.');
    } catch { notice('Выделите и скопируйте текст причины в блоке выше.', 'error'); }
  }
  async function perform(label, action) {
    if (state.busy) return;
    state.busy = label;
    notice(); sync();
    try { await action(); } catch (error) { report(error); }
    finally { state.busy = false; sync(); }
  }
  function acceptStatus(data) {
    acceptTemplates(data.templates || []); if (data.runtime) acceptRuntime(data.runtime);
    state.draft = clone(data.draft);
    state.saved = serialized();
    state.revision = data.revision;
    state.discovery = data.discovery;
    state.loaded = true;
    state.stale = false;
    state.version += 1;
    state.previewVersion = null;
    $('preview-section').hidden = true;
    render();
    schedulePoll();
  }
  async function reload() {
    if (dirty() && !confirm('Заменить ваши несохранённые правки сохранённым черновиком?')) return;
    await perform('Загрузка черновика…', async () => {
      acceptStatus(checkedStatus(await request('deviceprofilesstatus')));
      notice('Сохранённый черновик загружен. Рабочая стратегия не изменялась.');
    });
  }
  async function refreshDiscovery() {
    await perform('Обновление списка устройств…', async () => {
      const data = checkedStatus(await request('deviceprofilesstatus'));
      state.discovery = data.discovery;
      if (data.revision !== state.revision) state.stale = true;
      renderDiscovery();
      notice('Список известных устройств обновлён. Состав вашего черновика сохранён.');
    });
  }
  function payload() {
    const draft = clone(state.draft);
    draft.devices.forEach((d) => { d.name = d.name.trim(); });
    draft.profiles.forEach((p) => { p.name = p.name.trim(); });
    if (draft.devices.some((d) => !d.name) || draft.profiles.some((p) => !p.name)) throw userError('Укажите название для каждого устройства и профиля.');
    const value = JSON.stringify(draft);
    if (new TextEncoder().encode(value).length > 65536) throw userError('Черновик превышает допустимый размер 64 КБ. Уменьшите число устройств или профилей.');
    return value;
  }
  async function save() {
    await perform('Сохранение черновика…', async () => {
      const data = checkedStatus(await request('deviceprofilessave', { draft: payload(), revision: state.revision }));
      acceptStatus(data);
      notice('Черновик сохранён. Он будет доступен после перезагрузки страницы. Рабочая стратегия не изменена.');
    });
  }
  async function preview() {
    await perform('Проверка черновика…', async () => {
      const data = await request('deviceprofilespreview', { draft: payload() });
      if (data.schema_version !== 1 || data.applied !== false || !['common', 'split'].includes(data.mode) || !Array.isArray(data.assignments) || !Array.isArray(data.profiles) || !Array.isArray(data.warnings)) throw problem('invalid_response');
      renderPreview(data);
      state.previewVersion = state.version;
      $('preview-section').hidden = false;
      $('preview-title').tabIndex = -1;
      $('preview-title').focus({ preventScroll: true });
      $('preview-section').scrollIntoView({ behavior: 'auto', block: 'nearest' });
      notice('Предпросмотр готов. Черновик не сохранён этим действием, правила не применены.');
    });
  }

  function renderMode() {
    document.querySelectorAll('input[name="mode"]').forEach((input) => { input.checked = input.value === state.draft.mode; });
    $('profiles-section').hidden = state.draft.mode !== 'split';
    $('common-note').hidden = state.draft.mode !== 'common';
  }
  function deviceInfo(device) {
    const info = element('div', 'device-info');
    info.append(element('p', 'device-name', device.name || 'Без имени'));
    info.append(element('p', 'device-address', [...device.addresses, device.mac].filter(Boolean).join(' · ') || 'Адрес не указан'));
    return info;
  }
  function duplicate(device) {
    return state.draft.devices.some((d) => d.id === device.id ||
      (d.mac && device.mac && d.mac.toLowerCase() === device.mac.toLowerCase()) ||
      d.addresses.some((a) => device.addresses.includes(a)));
  }
  function addDevice(device) {
    if (state.draft.devices.length >= 128) { notice('Можно добавить не более 128 устройств.', 'error'); return; }
    if (duplicate(device)) { notice('Это устройство уже добавлено в черновик.', 'warning'); return; }
    state.draft.devices.push(clone(device));
    changed(); renderDevices(); renderDiscovery(); renderProfiles();
    notice('Устройство добавлено в черновик. Сохраните изменения, когда закончите.');
  }
  function renderDevices() {
    $('device-count').textContent = state.draft.devices.length + ' / 128';
    const nodes = state.draft.devices.map((device) => {
      const row = element('div', 'device-row');
      const remove = button('Убрать', () => {
        if (!confirm('Убрать «' + device.name + '» из черновика и всех профилей?')) return;
        state.draft.devices = state.draft.devices.filter((d) => d.id !== device.id);
        state.draft.profiles.forEach((p) => { p.device_ids = p.device_ids.filter((id) => id !== device.id); });
        changed(); renderDevices(); renderDiscovery(); renderProfiles();
      });
      remove.setAttribute('aria-label', 'Убрать устройство ' + device.name);
      row.append(deviceInfo(device), remove);
      return row;
    });
    $('draft-devices').replaceChildren(...(nodes.length ? nodes : [element('p', 'empty', 'В черновике пока нет устройств. Добавьте из списка ниже или укажите адрес вручную.')]));
  }
  function renderDiscovery() {
    const discovery = state.discovery;
    if (!discovery) return;
    const labels = { available: 'Список получен', partial: 'Доступна часть данных', unavailable: 'Обнаружение сейчас недоступно' };
    let suffix = '';
    if (typeof discovery.checked_at === 'string') {
      const time = new Date(discovery.checked_at);
      if (Number.isFinite(time.getTime())) suffix = ' · ' + time.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
    }
    $('discovery-status').textContent = labels[discovery.state] + suffix;
    const rows = discovery.devices.map((device) => {
      const row = element('div', 'device-row');
      const info = deviceInfo(device);
      const sources = device.sources.map((source) => ({ dhcp: 'DHCP', neighbor: 'таблица соседей' })[source] || 'другой источник');
      info.append(element('p', 'device-source', 'Источники: ' + (sources.join(', ') || 'не указаны')));
      const included = duplicate(device);
      const add = button(included ? 'Добавлено' : '+ В черновик', () => addDevice({
        id: device.id, name: device.name || device.mac || device.addresses[0] || 'Устройство',
        mac: device.mac, addresses: [...device.addresses],
      }));
      add.disabled = included || state.draft.devices.length >= 128;
      add.setAttribute('aria-label', included ? 'Устройство уже добавлено' : 'Добавить в черновик: ' + (device.name || device.mac || device.id));
      row.append(info, add);
      return row;
    });
    $('discovery-devices').replaceChildren(...(rows.length ? rows : [element('p', 'empty', discovery.state === 'unavailable'
      ? 'Не удалось прочитать список. Можно добавить устройство вручную по известному адресу.'
      : 'Известных устройств пока нет. Можно обновить список или добавить устройство вручную.')]));
  }
  function canonicalIP(value) {
    if (!value) return '';
    if (/^\d{1,3}(\.\d{1,3}){3}$/.test(value)) {
      const parts = value.split('.').map(Number);
      if (parts.some((part) => part > 255)) throw userError('Проверьте IPv4-адрес: каждое число должно быть от 0 до 255.');
      return parts.join('.');
    }
    if (value.includes(':') && /^[0-9a-fA-F:.]+$/.test(value)) {
      try {
        const host = new URL('http://[' + value + ']/').hostname;
        if (host.startsWith('[') && host.endsWith(']')) return host.slice(1, -1).toLowerCase();
      } catch { /* Report one human-readable address error below. */ }
    }
    throw userError('Укажите корректный IPv4 или IPv6 без маски подсети.');
  }
  function addManual(event) {
    event.preventDefault();
    $('manual-error').hidden = true;
    try {
      const name = $('manual-name').value.trim();
      const ip = canonicalIP($('manual-ip').value.trim());
      const rawMac = $('manual-mac').value.trim();
      let mac = '';
      if (rawMac) {
        const compact = rawMac.replace(/[:-]/g, '').toLowerCase();
        if (!/^[a-f0-9]{12}$/.test(compact)) throw userError('Укажите MAC-адрес из 12 шестнадцатеричных символов, например aa:bb:cc:dd:ee:ff.');
        mac = compact.match(/../g).join(':');
      }
      if (!name) throw userError('Укажите название устройства.');
      if (!ip && !mac) throw userError('Укажите IP или MAC устройства.');
      const device = { id: randomId('manual-'), name, mac, addresses: ip ? [ip] : [] };
      if (duplicate(device)) throw userError('Устройство с этим IP или MAC уже есть в черновике.');
      if (state.draft.devices.length >= 128) throw userError('Достигнут предел: 128 устройств.');
      addDevice(device);
      $('manual-form').reset();
      $('manual-name').focus();
    } catch (error) {
      $('manual-error').textContent = error.userMessage || 'Не удалось добавить устройство. Проверьте адреса.';
      $('manual-error').hidden = false;
    }
  }

  function moveProfile(id, offset) {
    const index = state.draft.profiles.findIndex((p) => p.id === id);
    const target = index + offset;
    if (index < 0 || target < 0 || target >= state.draft.profiles.length) return;
    const [profile] = state.draft.profiles.splice(index, 1);
    state.draft.profiles.splice(target, 0, profile);
    changed(); renderProfiles();
    const card = document.getElementById(id);
    const sameButton = card.querySelector(offset < 0 ? '.move-up' : '.move-down');
    (sameButton.disabled ? card.querySelector('.drag-handle') : sameButton).focus({ preventScroll: true });
  }
  function renderProfiles() {
    const nodes = state.draft.profiles.map((profile, index) => {
      const card = element('article', 'profile-card');
      card.id = profile.id;
      card.setAttribute('aria-label', 'Профиль ' + (index + 1) + ': ' + profile.name);
      const top = element('div', 'profile-top');
      const handle = button('⠿', () => {} , 'drag-handle');
      handle.draggable = true;
      handle.setAttribute('aria-label', 'Переместить профиль ' + (index + 1) + '. Клавиатура: Alt и стрелка вверх или вниз.');
      handle.title = 'Перетащить профиль; Alt + ↑ / ↓';
      handle.addEventListener('keydown', (event) => {
        if (event.altKey && ['ArrowUp', 'ArrowDown'].includes(event.key)) {
          event.preventDefault(); moveProfile(profile.id, event.key === 'ArrowUp' ? -1 : 1);
        }
      });
      handle.addEventListener('dragstart', (event) => {
        if (state.busy) { event.preventDefault(); return; }
        state.dragId = profile.id;
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('text/plain', profile.id);
        card.classList.add('dragging');
      });
      handle.addEventListener('dragend', () => {
        state.dragId = null;
        document.querySelectorAll('.profile-card').forEach((c) => c.classList.remove('dragging', 'drop-target'));
      });
      card.addEventListener('dragover', (event) => {
        if (!state.dragId || state.dragId === profile.id || state.busy) return;
        event.preventDefault(); event.dataTransfer.dropEffect = 'move'; card.classList.add('drop-target');
      });
      card.addEventListener('dragleave', (event) => { if (!card.contains(event.relatedTarget)) card.classList.remove('drop-target'); });
      card.addEventListener('drop', (event) => {
        if (!state.dragId || state.dragId === profile.id || state.busy) return;
        event.preventDefault();
        const source = state.draft.profiles.findIndex((p) => p.id === state.dragId);
        const target = state.draft.profiles.findIndex((p) => p.id === profile.id);
        if (source < 0 || target < 0) return;
        const [moved] = state.draft.profiles.splice(source, 1);
        state.draft.profiles.splice(target, 0, moved);
        state.dragId = null; changed(); renderProfiles();
        notice('Порядок приоритетов изменён в черновике. Сохраните изменения, когда закончите.');
      });
      const order = element('div', 'order-actions');
      const up = button('↑', () => moveProfile(profile.id, -1), 'move-up');
      up.disabled = index === 0;
      up.setAttribute('aria-label', 'Поднять профиль ' + profile.name);
      const down = button('↓', () => moveProfile(profile.id, 1), 'move-down');
      down.disabled = index === state.draft.profiles.length - 1;
      down.setAttribute('aria-label', 'Опустить профиль ' + profile.name);
      order.append(up, down);
      top.append(element('span', 'order-number', String(index + 1)), handle, element('span', 'profile-caption', 'Приоритет ' + (index + 1)), order);
      const fields = element('div', 'profile-fields');
      const nameLabel = element('label', 'field-label', 'Название профиля');
      const name = element('input');
      name.type = 'text'; name.maxLength = 64; name.value = profile.name;
      name.addEventListener('input', () => { profile.name = name.value; changed(); });
      nameLabel.append(name);
      const strategyLabel = element('label', 'field-label', 'Стратегия');
      const strategy = element('select');
      strategy.setAttribute('aria-label', 'Стратегия');
      for (const [value, label] of Object.entries(strategyNames)) {
        const option = element('option', '', label); option.value = value; strategy.append(option);
      }
      strategy.value = profile.strategy;
      if (!Object.hasOwn(strategyNames, profile.strategy)) {
        const missing = element('option', '', 'Недоступная стратегия'); missing.value = profile.strategy; missing.disabled = true; missing.selected = true; strategy.append(missing);
      }
      strategy.addEventListener('change', () => { profile.strategy = strategy.value; changed(); });
      strategyLabel.append(strategy);
      fields.append(nameLabel, strategyLabel);
      const controls = element('div', 'profile-controls');
      const enabledLabel = element('label', 'checkbox-label');
      const enabled = element('input'); enabled.type = 'checkbox'; enabled.checked = profile.enabled;
      enabled.addEventListener('change', () => { profile.enabled = enabled.checked; changed(); });
      enabledLabel.append(enabled, element('span', '', 'Профиль включён в черновике'));
      const remove = button('Удалить профиль', () => {
        if (!confirm('Удалить профиль «' + profile.name + '» из черновика?')) return;
        state.draft.profiles = state.draft.profiles.filter((p) => p.id !== profile.id);
        changed(); renderProfiles();
      }, 'danger');
      controls.append(enabledLabel, remove);
      const choices = element('div', 'device-choices');
      choices.setAttribute('role', 'group'); choices.setAttribute('aria-label', 'Устройства профиля ' + profile.name);
      state.draft.devices.forEach((device) => {
        const label = element('label', 'checkbox-label device-choice');
        const input = element('input'); input.type = 'checkbox'; input.checked = profile.device_ids.includes(device.id);
        input.addEventListener('change', () => {
          profile.device_ids = profile.device_ids.filter((id) => id !== device.id);
          if (input.checked) profile.device_ids.push(device.id);
          changed();
        });
        const text = element('span');
        text.append(element('span', 'choice-name', device.name), element('span', 'choice-address', [...device.addresses, device.mac].filter(Boolean).join(' · ')));
        label.append(input, text); choices.append(label);
      });
      if (!state.draft.devices.length) choices.append(element('p', 'empty', 'Сначала добавьте устройства в черновик.'));
      card.append(top, fields, controls, choices);
      return card;
    });
    $('profiles').replaceChildren(...(nodes.length ? nodes : [element('p', 'empty', 'Профилей пока нет. Добавьте профиль и выберите для него устройства.')]));
    sync();
  }
  function renderPreview(data) {
    const nodes = [];
    nodes.push(element('p', 'preview-info', data.mode === 'common'
      ? 'Общий режим: для всех устройств используется текущая стратегия. Подготовленные отдельные профили в этом режиме не участвуют.'
      : 'Для каждого устройства показаны включённые профили в порядке проверки. Если профиль не подходит, проверяется следующий; в конце остаётся текущая стратегия.'));
    data.assignments.forEach((assignment) => {
      if (!assignment || !Array.isArray(assignment.profile_ids)) throw problem('invalid_response');
      const device = state.draft.devices.find((d) => d.id === assignment.device_id);
      const row = element('div', 'preview-row');
      row.append(element('strong', '', device ? device.name : 'Устройство'));
      const candidates = data.mode === 'common' ? [] : assignment.profile_ids.map((id) => {
        const profile = data.profiles.find((p) => p.id === id);
        return profile ? profile.name + ' (' + (strategyNames[profile.strategy] || 'стратегия') + ')' : 'Неизвестный профиль';
      });
      row.append(element('p', '', candidates.length ? candidates.map((name, i) => (i + 1) + '. ' + name).join(' → ') + ' → Текущая стратегия (по умолчанию)' : 'Текущая стратегия (по умолчанию)'));
      nodes.push(row);
    });
    if (!data.assignments.length) nodes.push(element('p', 'empty', 'Устройств в черновике нет. Для остальных остаётся текущая стратегия.'));
    const warningNames = {
      empty_profile: 'Есть профиль без выбранных устройств.',
      unresolved_mac: 'Для MAC пока не удалось определить IP. Он остаётся в черновике; активное правило не создано.',
      no_profiles: 'В черновике нет отдельных профилей. Остаётся текущая стратегия.',
    };
    if (data.warnings.length) {
      const warnings = element('ul', 'preview-warnings');
      data.warnings.forEach((warning) => warnings.append(element('li', '', warningNames[warning] || 'Панель сообщила дополнительное предупреждение: ' + String(warning))));
      nodes.push(warnings);
    }
    $('preview-content').replaceChildren(...nodes);
  }
  function render() { renderMode(); renderDevices(); renderDiscovery(); renderProfiles(); sync(); }

  document.querySelectorAll('input[name="mode"]').forEach((input) => input.addEventListener('change', () => {
    if (input.checked) { state.draft.mode = input.value; changed(); renderMode(); }
  }));
  $('manual-form').addEventListener('submit', addManual);
  $('reload').addEventListener('click', reload);
  $('refresh').addEventListener('click', refreshDiscovery);
  $('preview').addEventListener('click', preview);
  $('save').addEventListener('click', save);
  $('apply').addEventListener('click', activate);
  $('runtime-refresh').addEventListener('click', () => perform('Обновление состояния…', async () => { acceptRuntime(await request('deviceprofilesruntime')); sync(); schedulePoll(); }));
  $('capture-current').addEventListener('click', captureCurrent);
  $('library-import').addEventListener('click', importFile);
  $('catalog-load').addEventListener('click', loadCatalog);
  $('catalog-add').addEventListener('click', addCatalog);
  $('catalog-profile').addEventListener('change', () => { $('catalog-description').textContent = state.catalog.find((p) => p.id === $('catalog-profile').value)?.description || ''; sync(); });
  $('copy-error').addEventListener('click', copyFailure);
  document.addEventListener('visibilitychange', schedulePoll);
  window.addEventListener('pagehide', () => clearTimeout(state.pollTimer));
  $('close-preview').addEventListener('click', () => { $('preview-section').hidden = true; });
  $('add-profile').addEventListener('click', () => {
    if (state.draft.profiles.length >= 16) return;
    const profile = { id: randomId('profile-'), name: 'Профиль ' + (state.draft.profiles.length + 1), enabled: true, strategy: 'current', device_ids: [] };
    state.draft.profiles.push(profile); changed(); renderProfiles();
    document.getElementById(profile.id).querySelector('input[type="text"]').focus();
  });
  window.addEventListener('beforeunload', (event) => {
    if (dirty()) { event.preventDefault(); event.returnValue = ''; }
  });
  reload();
})();
