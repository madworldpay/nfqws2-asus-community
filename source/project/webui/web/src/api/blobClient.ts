import { ShareError, shareRequest } from '@/api/shareClient';
import { sha256 } from '@/api/supportDigest';

export const MAX_BLOB_BYTES = 262144;
export type BlobFile = Readonly<{
  name: string;
  path: string;
  byte_length: number;
  sha256: string | null;
  state: 'available' | 'unavailable' | 'too_large';
  format: 'tls' | 'quic' | 'stun' | 'other';
  label: Readonly<{ ru: string; en: string }> | null;
  bundled: boolean;
}>;
export type BlobInventory = Readonly<{
  files: BlobFile[];
  skipped: number;
  scan_truncated: boolean;
}>;

const object = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);
const exact = (
  value: unknown,
  keys: string[],
): value is Record<string, unknown> =>
  object(value) &&
  Object.keys(value).length === keys.length &&
  keys.every((key) => key in value);
const integer = (value: unknown, min: number, max = Number.MAX_SAFE_INTEGER) =>
  Number.isSafeInteger(value) && Number(value) >= min && Number(value) <= max;
const hasControl = (value: string) =>
  Array.from(value).some(
    (c) => c.charCodeAt(0) < 32 || c.charCodeAt(0) === 127,
  );
const labelText = (value: unknown) =>
  typeof value === 'string' &&
  value.length > 0 &&
  new TextEncoder().encode(value).length <= 256 &&
  !hasControl(value);

function blobFile(value: unknown): BlobFile {
  if (
    !exact(value, [
      'name',
      'path',
      'byte_length',
      'sha256',
      'state',
      'format',
      'label',
      'bundled',
    ]) ||
    typeof value.name !== 'string' ||
    value.name.length > 128 ||
    !/^[A-Za-z0-9][A-Za-z0-9_.-]*\.bin$/i.test(value.name) ||
    (value.path !== `/opt/etc/nfqws2/blobs/${value.name}` &&
      value.path !== `/etc/nfqws2/blobs/${value.name}`) ||
    !integer(value.byte_length, 0) ||
    typeof value.state !== 'string' ||
    !['available', 'unavailable', 'too_large'].includes(value.state) ||
    typeof value.format !== 'string' ||
    !['tls', 'quic', 'stun', 'other'].includes(value.format) ||
    (value.sha256 !== null &&
      !(
        typeof value.sha256 === 'string' && /^[a-f0-9]{64}$/.test(value.sha256)
      )) ||
    (value.state === 'available' &&
      (!integer(value.byte_length, 1, MAX_BLOB_BYTES) ||
        value.sha256 === null)) ||
    (value.state !== 'available' && value.sha256 !== null) ||
    (value.label !== null &&
      !(
        exact(value.label, ['ru', 'en']) &&
        labelText(value.label.ru) &&
        labelText(value.label.en)
      )) ||
    typeof value.bundled !== 'boolean'
  )
    throw new ShareError('invalid_response');
  return value as unknown as BlobFile;
}

export async function loadBlobInventory(csrf: string): Promise<BlobInventory> {
  const value = await shareRequest(csrf, 'blobinventory', {}, 262144);
  if (
    !exact(value, ['files', 'skipped', 'scan_truncated']) ||
    !Array.isArray(value.files) ||
    value.files.length > 128 ||
    !integer(value.skipped, 0) ||
    typeof value.scan_truncated !== 'boolean'
  )
    throw new ShareError('invalid_response');
  const files = value.files.map(blobFile);
  if (new Set(files.map((file) => file.name)).size !== files.length)
    throw new ShareError('invalid_response');
  return {
    files,
    skipped: Number(value.skipped),
    scan_truncated: value.scan_truncated,
  };
}

export async function uploadBlob(csrf: string, file: File): Promise<BlobFile> {
  if (
    !/\.bin$/i.test(file.name) ||
    file.name.length > 255 ||
    hasControl(file.name) ||
    /[/\\]/.test(file.name)
  )
    throw new ShareError('invalid_name');
  if (file.size < 1) throw new ShareError('empty_file');
  if (file.size > MAX_BLOB_BYTES) throw new ShareError('file_too_large');
  const bytes = new Uint8Array(await file.arrayBuffer());
  if (bytes.byteLength !== file.size) throw new ShareError('source_changed');
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  const hash = sha256(bytes);
  const value = await shareRequest(
    csrf,
    'blobupload',
    {
      name: file.name,
      data_base64: btoa(binary),
      sha256: hash,
    },
    4096,
    20000,
  );
  if (!exact(value, ['file'])) throw new ShareError('invalid_response');
  const result = blobFile(value.file);
  if (
    result.state !== 'available' ||
    result.byte_length !== bytes.length ||
    result.sha256 !== hash
  )
    throw new ShareError('invalid_response');
  return result;
}
