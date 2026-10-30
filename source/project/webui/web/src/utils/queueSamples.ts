import type { AsusDiagnostics } from '../api/schema.ts';

type Queue = AsusDiagnostics['nfqueue'] & { lifetime?: string | null };
const counter = (value: unknown): value is number =>
  typeof value === 'number' &&
  Number.isInteger(value) &&
  value >= 0 &&
  value <= 4294967295;
const lifetime = (value: unknown): value is string =>
  typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);
export type QueueComparison =
  | {
      result: 'increased' | 'unchanged';
      before: number;
      after: number;
      delta: number;
    }
  | { result: 'reset' | 'unavailable' };

export const compareQueueSamples = (
  before?: Queue,
  after?: Queue,
): QueueComparison => {
  if (
    !before ||
    !after ||
    before.state !== 'bound' ||
    after.state !== 'bound' ||
    !counter(before.queue_number) ||
    before.queue_number > 65535 ||
    !counter(after.queue_number) ||
    after.queue_number > 65535 ||
    !counter(before.sequence) ||
    !counter(after.sequence) ||
    !lifetime(before.lifetime) ||
    !lifetime(after.lifetime)
  )
    return { result: 'unavailable' };
  if (
    before.queue_number !== after.queue_number ||
    before.lifetime !== after.lifetime ||
    after.sequence < before.sequence
  )
    return { result: 'reset' };
  // A uint32 wrap and a queue reset have the same observable decrease.
  // Retry instead of manufacturing packet growth with modulo arithmetic.
  const delta = after.sequence - before.sequence;
  return {
    result: delta > 0 ? 'increased' : 'unchanged',
    before: before.sequence,
    after: after.sequence,
    delta,
  };
};
