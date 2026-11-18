import assert from 'node:assert/strict';
import { mkdtemp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';
const src = fileURLToPath(new URL('../webui/web/src/', import.meta.url));
const dir = await mkdtemp(join(tmpdir(), 'dpi-custom-client-'));
await build({ entryPoints: [join(src, 'api/dpiSiteCheckClient.ts')], outfile: join(dir, 'client.mjs'), bundle: true, alias: { '@': src }, format: 'esm', platform: 'node', logLevel: 'silent' });
await build({ entryPoints: [join(src, 'utils/dpiSiteCheckDownload.ts')], outfile: join(dir, 'download.mjs'), bundle: true, alias: { '@': src }, format: 'esm', platform: 'node', logLevel: 'silent' });
const client = await import(pathToFileURL(join(dir, 'client.mjs')));
const download = await import(pathToFileURL(join(dir, 'download.mjs')));
if (process.argv.includes('--details')) {
 assert.equal(typeof download.dpiSiteTraceHops, 'function', 'Owner446 needs individual hop details');
 assert.deepEqual(download.dpiSiteTraceHops('traceroute to 1.1.1.1 (1.1.1.1), 12 hops max\n 1  192.168.1.1  0.25 ms\n 2  *\n 3  1.1.1.1  12.5 ms !H'), [
  {hop:1, addresses:['192.168.1.1'], times_ms:[0.25], unanswered:false, note:''},
  {hop:2, addresses:[], times_ms:[], unanswered:true, note:''},
  {hop:3, addresses:['1.1.1.1'], times_ms:[12.5], unanswered:false, note:'!H'},
 ]);
 const base={schema_version:2, kind:'domain', operation:'https', addresses:[], dns:{rcode:null,answers:[],reason:'system_no_address'},response:{outcome:'connection_error',error_code:'dns_failed',http_status:null}};
 assert.equal(download.dpiSiteDiagnosis(base), 'dns_failed');
 assert.equal(download.dpiSiteDiagnosis({...base,dns:{rcode:3,answers:[],reason:'rcode'}}), 'dns_nxdomain');
 assert.equal(download.dpiSiteDiagnosis({...base,response:{...base.response,outcome:'blocked_address'}}), 'dns_non_public');
 assert.equal(download.dpiSiteDiagnosis({...base,response:{outcome:'response',error_code:null,http_status:451}}), 'http_451');
 assert.equal(download.dpiSiteDiagnosis({...base,response:{outcome:'response',error_code:null,http_status:403}}), 'http_403');
 assert.equal(download.dpiSiteDiagnosis({...base,response:{outcome:'timeout',error_code:'deadline',http_status:null}}), 'timeout');
 assert.equal(download.dpiSiteDiagnosis({...base,kind:'ipv4',response:{outcome:'tls_error',error_code:'tls_verification_failed',http_status:null}}), 'ip_tls');
 assert.equal(download.dpiSiteDiagnosis({...base,response:{outcome:'response',error_code:null,http_status:200}}), 'http_received');
 console.log('PASS detailed hop parsing and evidence-qualified diagnostics');process.exit(0);
}
assert.equal(typeof client.checkDpiTarget, 'function', 'Existing diagnostics client must carry a custom public IP/domain request');
const context = { nfqws:'running', mode:'auto', config_sha256:'a'.repeat(64) };
const target = 'custom-route:1.1.1.1';
const piece = { state:'partial', output:'1  192.0.2.1  2 ms\n2  *' };
const report = { type:'nfqws2_dpi_site_check', schema_version:2, target, url:'https://1.1.1.1/', host:'1.1.1.1', kind:'ipv4', operation:'route', addresses:['1.1.1.1'], dns:{rcode:null,answers:[],reason:'not_requested'}, network:{ping:{state:'done',output:'3 packets transmitted, 3 received'},route:{state:'done',output:'1.1.1.1 via 192.0.2.1 dev ppp0'},trace:piece}, started_at:1, finished_at:2,context:{before:context,after:context,changed:false},response:{outcome:'unavailable',http_status:null,bytes_read:0,body_limited:false,redirect:null,elapsed_ms:123,error_code:'not_requested'},full_service_verified:false,dns_scope:'local_resolver' };
let posted;
const oldFetch = globalThis.fetch;
try {
 globalThis.fetch = async (url, options) => { posted = Object.fromEntries(options.body); return Response.json(report); };
 assert.deepEqual(await client.checkDpiTarget('csrf','1.1.1.1','route','local_resolver'), report);
 assert.deepEqual(posted, {cmd:'dpisitecheck',csrf_token:'csrf',target,dns_scope:'local_resolver'});
 const text = download.buildDpiSiteCheckText('custom',[report], key=>key);
 assert.ok(text.includes(piece.output));
 assert.ok(text.includes('1.1.1.1'));
 assert.ok(text.includes('full_service_verified=false'));
 globalThis.fetch = async () => Response.json({...report, target:'custom-route:8.8.8.8'});
 await assert.rejects(client.checkDpiTarget('csrf','1.1.1.1','route','local_resolver'), e=>e.code==='invalid_response');
} finally { globalThis.fetch = oldFetch; }
console.log('PASS custom route request, bound response and TXT observations');
