import type { TFunction } from '@/context/TranslationProvider';

import type { DpiCustomSiteCheck, DpiSiteObservation, DpiSiteService } from '@/api/dpiSiteCheckClient';

/** Numeric traceroute output only; a star is an unanswered probe, not a loss rate. */
export function dpiSiteTraceHops(output: string) {
  return output.split(/\r?\n/).flatMap(line => {
    const match = /^\s*(\d{1,2})\s+(.*)$/.exec(line);
    if (!match || Number(match[1]) < 1 || Number(match[1]) > 12) return [];
    const text = match[2];
    const addresses = [...new Set((text.match(/\b(?:\d{1,3}\.){3}\d{1,3}\b/g) ?? []).filter(ip => ip.split('.').every(n => Number(n) <= 255)))];
    const times_ms = [...text.matchAll(/(?:^|\s)([0-9]+(?:\.[0-9]+)?)\s*ms\b/g)].map(m => Number(m[1]));
    return [{hop:Number(match[1]),addresses,times_ms,unanswered:text.includes('*'),note:(text.match(/![A-Z0-9]+/g) ?? []).join(' ')}];
  });
}

/** Name only observed symptoms. No resolver comparison or block-page attribution is implied. */
export function dpiSiteDiagnosis(report: DpiCustomSiteCheck) {
  const r = report.response;
  if (report.kind === 'domain' && r.outcome === 'blocked_address') return 'dns_non_public';
  if (report.dns.rcode === 3) return 'dns_nxdomain';
  if (report.dns.rcode !== null && report.dns.rcode !== 0) return 'dns_error';
  if (r.error_code === 'dns_failed') return 'dns_failed';
  if (report.operation === 'route') return 'route_only';
  if (r.http_status === 451) return 'http_451';
  if (r.http_status === 403) return 'http_403';
  if (r.http_status !== null) return 'http_received';
  if (r.outcome === 'tls_error') return report.kind === 'ipv4' ? 'ip_tls' : 'tls';
  if (r.outcome === 'timeout') return 'timeout';
  if (r.outcome === 'connection_error') return 'connection';
  return 'unknown';
}

export function dpiSiteClockChanged(report: DpiSiteObservation): boolean {
  return report.finished_at < report.started_at;
}

export function dpiSiteResponseLabel(
  report: DpiSiteObservation,
  t: TFunction,
): string {
  if (report.schema_version === 2 && report.operation === 'route' && report.addresses.length > 0) return t('dpi_site_check.route_observation');
  const r = report.response;
  if (r.error_code === 'dns_failed') return t('dpi_site_check.dns_failed');
  if (r.outcome !== 'response' && r.outcome !== 'read_limited')
    return t(`dpi_site_check.outcome_${r.outcome}`);
  if (
    /-(cdn|images|static|gateway)$/.test(report.target) &&
    (r.http_status === 403 || r.http_status === 404)
  )
    return t('dpi_site_check.endpoint_response');
  if (r.http_status !== null && r.http_status >= 400)
    return t('dpi_site_check.http_error');
  if (r.body_limited || r.outcome === 'read_limited')
    return t('dpi_site_check.read_limited');
  if (r.outcome !== 'response') return t(`dpi_site_check.outcome_${r.outcome}`);
  if (r.http_status !== null && r.http_status >= 300)
    return t('dpi_site_check.redirect_response');
  return t('dpi_site_check.http_response');
}

export function dpiSiteContextLabel(
  changed: boolean | null,
  t: TFunction,
): string {
  return t(
    changed === null
      ? 'dpi_site_check.unknown'
      : changed
        ? 'dpi_site_check.changed'
        : 'dpi_site_check.unchanged',
  );
}

export function buildDpiSiteCheckText(
  service: DpiSiteService,
  reports: readonly DpiSiteObservation[],
  t: TFunction,
): string {
  const lines = [
    `NFQWS2 — ${t('dpi_site_check.title')}: ${t(`dpi_site_check.service_${service}`)}`,
    t(service === 'custom' ? 'dpi_site_check.custom_scope' : 'dpi_site_check.incomplete'),
    t('dpi_site_check.dns_scope'),
    t('dpi_site_check.snapshot_scope'),
    'full_service_verified=false',
    '',
  ];
  for (const report of reports) {
    lines.push(
      `${report.target} — ${report.url}`,
      ...(report.schema_version === 2 ? [
        `${t('dpi_site_check.resolved')}: ${report.addresses.join(', ') || '—'}`,
        `${t('dpi_site_check.dns_answer')}: ${report.dns.answers.join(', ') || '—'}; RCODE=${report.dns.rcode ?? '—'}; ${report.dns.reason}`,
        t(`dpi_site_check.diagnosis_${dpiSiteDiagnosis(report)}`), t('dpi_site_check.diagnosis_limit'),
      ] : []),
      t(`dpi_site_check.dns_${report.dns_scope}`),
      report.schema_version === 2 && report.operation === 'route' ? dpiSiteResponseLabel(report, t) : `${dpiSiteResponseLabel(report, t)}; HTTP ${report.response.http_status ?? '—'}`,
      `${t('dpi_site_check.context')}: ${dpiSiteContextLabel(report.context.changed, t)}`,
      `${t('dpi_site_check.before')} / ${t('dpi_site_check.after')}:`,
      ...(dpiSiteClockChanged(report)
        ? [t('dpi_site_check.clock_changed')]
        : []),
      ...(report.schema_version === 2 && report.network ? (['ping','route','trace'] as const).flatMap(kind => [`${t(`dpi_site_check.network_${kind}`)}: ${t(`dpi_site_check.network_${report.network![kind].state}`)}`, report.network![kind].output]) : []),
      JSON.stringify(report, null, 2),
      '',
    );
  }
  return `${lines.join('\n')}\n`;
}

export function downloadDpiSiteCheck(
  service: DpiSiteService,
  reports: readonly DpiSiteObservation[],
  t: TFunction,
): void {
  const blob = new Blob([buildDpiSiteCheckText(service, reports, t)], {
    type: 'text/plain;charset=utf-8',
  });
  const link = document.createElement('a');
  const url = URL.createObjectURL(blob);
  try {
    link.href = url;
    link.download = `NFQWS2_SERVICE_${service}_${reports[0]?.started_at ?? 'partial'}.txt`;
    document.body.append(link);
    link.click();
  } finally {
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  }
}
