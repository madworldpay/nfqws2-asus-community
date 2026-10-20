import type { AsusDiagnostics } from '../api/schema.ts';

type Queue = AsusDiagnostics['nfqueue'];
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
    before.queue_number === null ||
    after.queue_number === null ||
    before.sequence === null ||
    after.sequence === null
  )
    return { result: 'unavailable' };
  if (
    before.queue_number !== after.queue_number ||
    after.sequence < before.sequence
  )
    return { result: 'reset' };
  const delta = after.sequence - before.sequence;
  return {
    result: delta > 0 ? 'increased' : 'unchanged',
    before: before.sequence,
    after: after.sequence,
    delta,
  };
};
