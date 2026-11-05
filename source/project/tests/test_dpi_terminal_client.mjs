import assert from 'node:assert/strict';
import * as dpi from '../webui/web/src/api/dpiClient.ts';

// Missing terminal entry points must fail before any network action is added.
assert.equal(typeof dpi.getDpiTerminalInfo, 'function');
assert.equal(typeof dpi.DpiTerminalSession, 'function');
const id = 'a'.repeat(32);
const requestId = '1'.repeat(32);
const fixture = (extra = {}) => ({ terminal_id: id, state: 'running', offset: 0, data: '', exit_code: null, ...extra });
let calls = [];
let response = { available: true, installed: true, code: null };
globalThis.fetch = async (url, options) => {
  calls.push({ url, options });
  return Response.json(response);
};
assert.deepEqual(await dpi.getDpiTerminalInfo('csrf'), response);
assert.equal(calls.length, 1);
assert.equal(calls[0].options.body.get('cmd'), 'dpiterminalinfo');
assert.equal(calls[0].options.body.get('csrf_token'), 'csrf');
assert.equal(calls[0].options.credentials, 'same-origin');
response = fixture();
await dpi.startDpiTerminal('csrf', 100, 24, 'ru', requestId);
assert.deepEqual(Object.fromEntries(calls.at(-1).options.body), { cmd: 'dpiterminalstart', csrf_token: 'csrf', cols: '100', rows: '24', language: 'ru', request_id: requestId });
await dpi.inputDpiTerminal('csrf', id, '\u001b[A');
assert.equal(calls.at(-1).options.body.get('data'), 'G1tB');
await dpi.pollDpiTerminal('csrf', id, 37);
assert.equal(calls.at(-1).options.body.get('offset'), '37');
await dpi.resizeDpiTerminal('csrf', id, 80, 20);
await dpi.stopDpiTerminal('csrf', id);
assert.equal(calls.at(-1).options.keepalive, true);
const before = calls.length;
for (const run of [
  () => dpi.startDpiTerminal('csrf', 0, 24, 'en', requestId),
  () => dpi.startDpiTerminal('csrf', 80, 24, 'xx', requestId),
  () => dpi.startDpiTerminal('csrf', 80, 24, 'en', 'invalid-request-id'),
  () => dpi.inputDpiTerminal('csrf', 'not-a-session', 'q'),
  () => dpi.inputDpiTerminal('csrf', id, 'я'.repeat(513)),
  () => dpi.pollDpiTerminal('csrf', id, -1),
]) await assert.rejects(run, { code: 'invalid_request' });
assert.equal(calls.length, before);
for (const bad of [fixture({ data: '@@@@' }), fixture({ data: btoa('x'.repeat(32769)) }), fixture({ state: 'shell' }), fixture({ offset: 0.2 }), fixture({ terminal_id: 'wrong' })]) {
  response = bad;
  await assert.rejects(dpi.pollDpiTerminal('csrf', id, 0), { code: 'invalid_response' });
}
response = fixture({ data: btoa('\u001b[31mNative menu\r\n'), offset: 18 });
assert.equal((await dpi.pollDpiTerminal('csrf', id, 0)).data, response.data);
console.log('PASS terminal API uses CSRF, bounded raw bytes and safe request validation');

// A lost start reply must recover the same owner, keep offset across input and
// resize replies, serialize all requests, and stop after a close during start.
let starts = 0, active = 0, maximumActive = 0, startNonces = [];
let pollOffsets = [], outputs = [], states = [], errors = [], stopped = 0;
let releaseSecondPoll;
const secondPoll = new Promise((resolve) => { releaseSecondPoll = resolve; });
globalThis.fetch = async (_url, options) => {
  const body = options.body;
  active++; maximumActive = Math.max(maximumActive, active);
  try {
    switch (body.get('cmd')) {
      case 'dpiterminalstart':
        startNonces.push(body.get('request_id'));
        if (++starts === 1) throw new TypeError('lost reply');
        return Response.json(fixture());
      case 'dpiterminalpoll': {
        const offset = Number(body.get('offset')); pollOffsets.push(offset);
        if (pollOffsets.length === 1) return Response.json(fixture({ data: btoa('abc'), offset: 3 }));
        await secondPoll;
        return Response.json(fixture({ state: 'exited', data: btoa('!'), offset: 4, exit_code: 0 }));
      }
      case 'dpiterminalinput':
      case 'dpiterminalresize': return Response.json(fixture());
      case 'dpiterminalstop': stopped++; return Response.json(fixture({ state: 'stopped' }));
      default: throw new Error('unexpected request');
    }
  } finally { active--; }
};
const session = new dpi.DpiTerminalSession('csrf', 'en', {
  output: (data) => { outputs.push(new TextDecoder().decode(data)); if (outputs.length === 1) { session.input('\u001b[B'); session.resize(100, 25); } },
  state: (state) => states.push(state), error: (error) => errors.push(error),
});
const running = session.start(80, 24);
await new Promise((resolve) => setTimeout(resolve, 400));
releaseSecondPoll();
await running;
await session.close();
assert.equal(starts, 2);
assert.match(startNonces[0], /^[a-f0-9]{32}$/);
assert.equal(startNonces[0], startNonces[1], 'lost start retry keeps the same request ownership');
assert.equal(maximumActive, 1);
assert.deepEqual(pollOffsets, [0, 3]);
assert.deepEqual(outputs, ['abc', '!']);
assert.equal(states.at(-1), 'exited');
assert.deepEqual(errors, []);
assert.equal(stopped, 1);
let releaseStart;
const delayedStart = new Promise((resolve) => { releaseStart = resolve; });
stopped = 0; outputs = [];
globalThis.fetch = async (_url, options) => {
  if (options.body.get('cmd') === 'dpiterminalstart') { await delayedStart; return Response.json(fixture({ data: btoa('late'), offset: 4 })); }
  assert.equal(options.body.get('cmd'), 'dpiterminalstop');
  stopped++; return Response.json(fixture({ state: 'stopped' }));
};
const closing = new dpi.DpiTerminalSession('csrf', 'en', { output: (data) => outputs.push(data), state: () => {}, error: () => {} });
const starting = closing.start(80, 24);
const closed = closing.close();
releaseStart();
await Promise.all([starting, closed]);
assert.equal(stopped, 1);
assert.deepEqual(outputs, []);
console.log('PASS terminal lifecycle recovers lost start, serializes polling, preserves cursor, stops late start');

let releasePoll, pollStarted;
const pendingPoll = new Promise((resolve) => { releasePoll = resolve; });
const polling = new Promise((resolve) => { pollStarted = resolve; });
stopped = 0;
globalThis.fetch = async (_url, options) => {
  switch (options.body.get('cmd')) {
    case 'dpiterminalstart': return Response.json(fixture());
    case 'dpiterminalpoll': pollStarted(); await pendingPoll; return Response.json(fixture());
    case 'dpiterminalstop': stopped++; return Response.json(fixture({ state: 'stopped' }));
    default: throw new Error('unexpected request');
  }
};
const leaving = new dpi.DpiTerminalSession('csrf', 'en', { output: () => {}, state: () => {}, error: () => {} });
const leavingRun = leaving.start(80, 24);
await polling;
const leave = leaving.close();
await new Promise((resolve) => setTimeout(resolve, 10));
assert.equal(stopped, 1, 'close sends keepalive stop immediately while a poll is pending');
releasePoll();
await Promise.all([leave, leavingRun]);
assert.equal(stopped, 1);
console.log('PASS terminal close immediately stops a process with an outstanding poll');

// Native final state can arrive before all of its spooled bytes have been read.
// An exact multiple of the wire chunk size requires a final empty poll.
for (const [finalState, total, expectedOffsets] of [
  ['exited', 98321, [0, 32768, 65536, 98304]],
  ['output_limit', 98304, [0, 32768, 65536, 98304]],
  ['expired', 65537, [0, 32768, 65536]],
]) {
  const spool = 'x'.repeat(total);
  let received = '', inputs = 0, resizes = 0, offsets = [];
  globalThis.fetch = async (_url, options) => {
    const body = options.body;
    switch (body.get('cmd')) {
      case 'dpiterminalstart': return Response.json(fixture());
      case 'dpiterminalpoll': {
        const offset = Number(body.get('offset'));
        offsets.push(offset);
        const chunk = spool.slice(offset, offset + 32768);
        return Response.json(fixture({ state: finalState, data: btoa(chunk), offset: offset + chunk.length, exit_code: finalState === 'exited' ? 0 : null }));
      }
      case 'dpiterminalinput': inputs++; return Response.json(fixture());
      case 'dpiterminalresize': resizes++; return Response.json(fixture());
      case 'dpiterminalstop': return Response.json(fixture({ state: 'stopped' }));
      default: throw new Error('unexpected request');
    }
  };
  const draining = new dpi.DpiTerminalSession('csrf', 'en', {
    output: (bytes) => {
      received += new TextDecoder().decode(bytes);
      if (received.length === 32768) { draining.input('s'); draining.resize(120, 30); }
    },
    state: () => {},
    error: (error) => assert.fail(`unexpected drain error: ${error.code}`),
  });
  await draining.start(80, 24);
  await draining.close();
  assert.equal(received.length, total, `${finalState}: all final output bytes must be drained`);
  assert.equal(received, spool);
  assert.deepEqual(offsets, expectedOffsets, `${finalState}: cursor survives empty control replies`);
  assert.equal(inputs, 1);
  assert.equal(resizes, 1);
}
console.log('PASS final exited/output_limit/expired output drains multiple chunks and exact multiples');

// Closing dialog A before its start reply cannot give its process to a newly
// opened dialog B. B must receive busy until A's owned process has been stopped.
let releaseOldStart;
const oldStartReply = new Promise((resolve) => { releaseOldStart = resolve; });
const otherId = 'b'.repeat(32);
let owner = null, issued = 0, nonceHistory = [], stoppedIds = [];
globalThis.fetch = async (_url, options) => {
  const body = options.body;
  if (body.get('cmd') === 'dpiterminalstart') {
    const nonce = body.get('request_id'); nonceHistory.push(nonce);
    if (owner) {
      if (owner.nonce !== nonce) return Response.json({ error: 'terminal_busy' }, { status: 409 });
      return Response.json(fixture({ terminal_id: owner.id }));
    }
    owner = { nonce, id: ++issued === 1 ? id : otherId };
    const startedId = owner.id;
    if (issued === 1) await oldStartReply;
    return Response.json(fixture({ terminal_id: startedId }));
  }
  const terminalId = body.get('terminal_id');
  if (body.get('cmd') === 'dpiterminalpoll') return Response.json(fixture({ terminal_id: terminalId, state: 'exited', exit_code: 0 }));
  assert.equal(body.get('cmd'), 'dpiterminalstop');
  stoppedIds.push(terminalId);
  if (owner?.id === terminalId) owner = null;
  return Response.json(fixture({ terminal_id: terminalId, state: 'stopped' }));
};
const oldDialog = new dpi.DpiTerminalSession('csrf', 'en', { output: () => {}, state: () => {}, error: () => {} });
const oldRun = oldDialog.start(80, 24);
const oldClose = oldDialog.close();
let newStates = [], newErrors = [];
const newDialog = new dpi.DpiTerminalSession('csrf', 'en', { output: () => {}, state: (value) => newStates.push(value), error: (error) => newErrors.push(error.code) });
await newDialog.start(80, 24);
assert.deepEqual(newErrors, ['terminal_busy']);
assert.deepEqual(newStates, ['failed']);
assert.deepEqual(stoppedIds, [], 'the busy dialog cannot stop the old dialog process');
assert.notEqual(nonceHistory[0], nonceHistory[1]);
releaseOldStart();
await Promise.all([oldRun, oldClose]);
assert.deepEqual(stoppedIds, [id]);
const explicitRetry = new dpi.DpiTerminalSession('csrf', 'en', { output: () => {}, state: () => {}, error: (error) => assert.fail(error.code) });
await explicitRetry.start(80, 24);
assert.equal(owner.id, otherId);
assert.equal(new Set(nonceHistory).size, 3, 'each explicit new session has a distinct nonce');
assert.deepEqual(stoppedIds, [id], 'old cleanup never stops the newly owned process');
await explicitRetry.close();
await newDialog.close();
assert.deepEqual(stoppedIds, [id, otherId]);
console.log('PASS close/reopen ownership uses distinct nonces and never attaches or stops another session');

let removalBody;
globalThis.fetch = async (_url, options) => {
 removalBody=Object.fromEntries(options.body);
 return Response.json({removed:true,reports_removed:options.body.get('delete_reports')==='1'});
};
assert.deepEqual(await dpi.removeDpiDetector('csrf',false),{removed:true,reports_removed:false});
assert.deepEqual(removalBody,{cmd:'dpiterminalremove',csrf_token:'csrf',consent:'remove',delete_reports:'0'});
assert.deepEqual(await dpi.removeDpiDetector('csrf',true),{removed:true,reports_removed:true});
assert.equal(removalBody.delete_reports,'1');
await assert.rejects(()=>dpi.removeDpiDetector('csrf','yes'),{code:'invalid_request'});
globalThis.fetch=async()=>Response.json({removed:true,reports_removed:true});
await assert.rejects(()=>dpi.removeDpiDetector('csrf',false),{code:'invalid_response'});
console.log('PASS removal uses explicit consent, CSRF and opt-in report deletion');
