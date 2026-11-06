import { readSaved, ShareError, type SavedReport } from '@/api/shareClient';

export async function downloadDpiSavedReport(
  csrfToken: string,
  report: SavedReport,
): Promise<void> {
  // readSaved enforces the native TXT name, size limit and HTTP-safe SHA-256.
  const file = await readSaved(csrfToken, report.id);
  const bytes = new TextEncoder().encode(file.raw);
  if (
    file.filename !== report.filename ||
    file.sha256 !== report.sha256 ||
    bytes.byteLength !== report.bytes
  )
    throw new ShareError('invalid_response');

  // Encode once without newline conversion or a BOM so the original hash holds.
  const blob = new Blob([bytes], { type: 'text/plain;charset=utf-8' });
  const link = document.createElement('a');
  const url = URL.createObjectURL(blob);
  try {
    link.href = url;
    link.download = file.filename;
    document.body.append(link);
    link.click();
  } finally {
    link.remove();
    // Keep the URL alive while the browser starts reading it. This timer is
    // independent of the dialog lifecycle, including immediate window closure.
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  }
}
