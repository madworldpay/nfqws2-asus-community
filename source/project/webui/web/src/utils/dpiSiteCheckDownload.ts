import type { TFunction } from '@/context/TranslationProvider';

import type { DpiSiteCheck, DpiSiteService } from '@/api/dpiSiteCheckClient';

export function dpiSiteClockChanged(report: DpiSiteCheck): boolean {
  return report.finished_at < report.started_at;
}

export function dpiSiteResponseLabel(
  report: DpiSiteCheck,
  t: TFunction,
): string {
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
  reports: readonly DpiSiteCheck[],
  t: TFunction,
): string {
  const lines = [
    `NFQWS2 — ${t('dpi_site_check.title')}: ${t(`dpi_site_check.service_${service}`)}`,
    t('dpi_site_check.incomplete'),
    t('dpi_site_check.dns_scope'),
    t('dpi_site_check.snapshot_scope'),
    'full_service_verified=false',
    '',
  ];
  for (const report of reports) {
    lines.push(
      `${report.target} — ${report.url}`,
      t(`dpi_site_check.dns_${report.dns_scope}`),
      `${dpiSiteResponseLabel(report, t)}; HTTP ${report.response.http_status ?? '—'}`,
      `${t('dpi_site_check.context')}: ${dpiSiteContextLabel(report.context.changed, t)}`,
      `${t('dpi_site_check.before')} / ${t('dpi_site_check.after')}:`,
      ...(dpiSiteClockChanged(report)
        ? [t('dpi_site_check.clock_changed')]
        : []),
      JSON.stringify(report, null, 2),
      '',
    );
  }
  return `${lines.join('\n')}\n`;
}

export function downloadDpiSiteCheck(
  service: DpiSiteService,
  reports: readonly DpiSiteCheck[],
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
