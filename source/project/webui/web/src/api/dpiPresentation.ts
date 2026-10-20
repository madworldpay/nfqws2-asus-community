export type DpiCell = { text: string; tone: 'success' | 'warning' | 'neutral' };
export type DpiTable = {
  group: number;
  headers: string[];
  rows: DpiCell[][];
  note?: string;
};
const text = (v: unknown): string =>
  v === null || v === undefined
    ? '—'
    : typeof v === 'object'
      ? JSON.stringify(v)
      : String(v);
const cell = (v: unknown): DpiCell => ({ text: text(v), tone: 'neutral' });
function measured(status: unknown, detail: unknown): DpiCell {
  let d = text(detail);
  if (detail === '') d = '';
  d = d
    .replace(/^http_(\d+)$/, 'HTTP $1')
    .replace(/^elapsed_(\d+)ms$/, '$1 ms')
    .replace(/_at_([0-9.]+)kb$/, ' @ $1 KiB');
  return {
    text: `${text(status)}${d && d !== '—' ? ` · ${d}` : ''}`,
    tone:
      status === 'ok' || status === 'quic_ok'
        ? 'success'
        : status === 'unknown' || status === null || status === undefined
          ? 'neutral'
          : 'warning',
  };
}
const record = (v: unknown): Record<string, unknown> =>
  v && typeof v === 'object' && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : {};
const list = (v: unknown): Record<string, unknown>[] =>
  Array.isArray(v) ? v.map(record) : [];
export function presentDpiNative(value: unknown, language: string): DpiTable[] {
  const root = record(value);
  if (root.type !== 'nfqws2_dpi_native') return [];
  const ru = language === 'ru';
  const tables: DpiTable[] = [];
  for (const g of list(root.groups)) {
    const results = record(record(g.document).results);
    const group = Number(g.group);
    const rows: DpiCell[][] = [];
    let headers: string[] = [];
    let note: string | undefined;
    if (group === 0) {
      headers = [
        ru ? 'Параметр' : 'Parameter',
        ru ? 'Наблюдение' : 'Observation',
      ];
      for (const [key, v] of Object.entries(record(results.network_info)))
        rows.push([cell(key), cell(v)]);
    }
    if (group === 1) {
      const r = record(results.dns_availability);
      headers = [
        ru ? 'Протокол / параметр' : 'Protocol / metric',
        ru ? 'Результат' : 'Result',
      ];
      for (const p of ['udp', 'doh', 'dot'])
        rows.push([
          cell(p.toUpperCase()),
          cell(`${text(r[p + '_ok'])} / ${text(r[p + '_total'])}`),
        ]);
      for (const k of [
        'resolvers_total',
        'subst_sub',
        'subst_total',
        'fakeip_sub',
        'hijacked_brands',
      ])
        rows.push([cell(k), cell(r[k])]);
      note = ru
        ? 'Ниже показаны только сбои DNS. Оригинальный JSON не содержит отдельных успешных ответов всех резолверов.'
        : 'DNS failures are listed below. The native JSON does not include individual successful replies for all resolvers.';
      tables.push({ group, headers, rows, note });
      tables.push({
        group,
        headers: [
          'Provider',
          'Protocol',
          'Endpoint',
          'OK / Total',
          'Status / Detail',
        ],
        rows: list(r.failures).map((x) => [
          cell(x.provider),
          cell(x.protocol),
          cell(x.endpoint),
          cell(`${text(x.ok)} / ${text(x.total)}`),
          measured(x.status, x.detail),
        ]),
      });
      continue;
    }
    if (group === 2) {
      headers = [
        ru ? 'Домен' : 'Domain',
        'IP',
        'HTTP',
        'TLS 1.2',
        'TLS 1.3',
        'QUIC',
      ];
      for (const r of list(results.domain_inspection))
        rows.push([
          cell(r.domain),
          cell(r.resolved),
          ...['http', 'tls12', 'tls13', 'quic'].map((p) =>
            measured(r[p], r[p + '_detail']),
          ),
        ]);
    }
    if (group === 3) {
      headers = [
        'ID',
        'ASN',
        'Provider',
        ru ? 'Результат / время / обрыв' : 'Result / time / cutoff',
      ];
      for (const r of list(results.tcp16))
        rows.push([
          cell(r.id),
          cell(r.asn),
          cell(r.provider),
          measured(r.status, r.detail),
        ]);
    }
    if (group === 4) {
      headers = [ru ? 'Параметр' : 'Parameter', ru ? 'Результат' : 'Result'];
      for (const [k, v] of Object.entries(record(results.whitelist_sni)))
        rows.push([cell(k), cell(v)]);
    }
    if (group === 5) {
      const r = record(results.telegram);
      headers = [
        ru ? 'Направление' : 'Direction',
        'Status',
        'Average, bit/s',
        'Peak, bit/s',
        'Bytes',
        'Drop, s',
      ];
      for (const direction of ['download', 'upload']) {
        const x = record(r[direction]);
        rows.push([
          cell(direction),
          measured(x.status, ''),
          cell(x.avg_bps),
          cell(x.peak_bps),
          cell(x.bytes),
          cell(x.drop_at_sec),
        ]);
      }
      note = `DC: ${text(r.dc_reachable)} / ${text(r.dc_total)} · ${text(r.verdict)}`;
    }
    if (group === 6) {
      const r = record(results.fingerprint_burst);
      headers = [
        ru ? 'Домен' : 'Domain',
        'IP',
        'Fingerprint',
        'Answered / Attempts',
        'Statuses',
        'Detail',
      ];
      for (const d of list(r.domains))
        for (const [profile, v] of Object.entries(record(d.profiles))) {
          const x = record(v);
          rows.push([
            cell(d.domain),
            cell(d.resolved),
            cell(profile),
            cell(`${text(x.answered)} / ${text(x.attempts)}`),
            cell(x.statuses),
            cell(x.detail),
          ]);
        }
      note = `TLS ${text(r.tls)} · ALPN ${text(r.alpn)} · ${text(r.attempts)} attempts · gap ${text(r.gap_ms)} ms · timeout ${text(r.timeout_secs)} s · variant ${text(r.variant)}`;
    }
    if (headers.length) tables.push({ group, headers, rows, note });
  }
  return tables;
}
