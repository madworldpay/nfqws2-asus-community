import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import {DNS_PRESETS,applyDnsPreset,findDnsPreset,selectedDnsPreset} from '../webui/web/src/api/smartDnsPresets.ts';
import {newUpstream} from '../webui/web/src/api/smartDnsProfile.ts';
const native=JSON.parse(readFileSync(new URL('../support/dpi-native-defaults.json',import.meta.url))).config;
const dpi=JSON.parse(readFileSync(new URL('../support/dpi-catalog.json',import.meta.url)));
test('all native DPI DoT/DoH endpoints are offered with explicit addresses and strict TLS',()=>{
 const nativeRows=native.DNS_AVAILABILITY_SERVERS.filter(x=>['dot','doh_wire'].includes(x[2]));
 assert.equal(nativeRows.length,71);assert.ok(DNS_PRESETS.length>=71);
 assert.equal(new Set(DNS_PRESETS.map(x=>x.id)).size,DNS_PRESETS.length);
 assert.equal(new Set(DNS_PRESETS.map(x=>x.label)).size,DNS_PRESETS.length);
 for(const [endpoint,,proto] of nativeRows){const p=DNS_PRESETS.find(x=>x.protocol===(proto==='dot'?'dot':'doh')&&(x.url||x.address)===endpoint);assert.ok(p,endpoint);assert.ok(p.bootstrap.length>0,endpoint);assert.ok(!/^\d+(\.\d+){3}$/.test(p.tls_name));if(proto==='doh_wire')assert.equal(p.port,Number(new URL(endpoint).port)||443);}
 for(const p of DNS_PRESETS)assert.ok(p.bootstrap.every(x=>/^\d+(\.\d+){3}$/.test(x)));
 for(const row of dpi.profile.dns.filter(x=>['dot','doh_wire'].includes(x.protocol))){const p=DNS_PRESETS.find(x=>x.id===row.id);assert.ok(p);assert.equal(p.url||p.address,row.endpoint);}
});
test('choosing a resolver fills connection fields without losing sites, scope or card identity',()=>{
 const original={...newUpstream('site_dns'),label:'TMDB',default:false,domains:[{name:'image.tmdb.org',include_subdomains:true}]};
 const next=applyDnsPreset(original,'quad9-doh');assert.equal(next.label,'TMDB');assert.equal(next.id,'site_dns');assert.equal(next.default,false);assert.deepEqual(next.domains,original.domains);assert.equal(next.protocol,'doh');assert.equal(next.port,443);assert.equal(next.url,'https://dns.quad9.net/dns-query');assert.equal(findDnsPreset(next)?.id,'quad9-doh');assert.equal(original.url,'');
});
test('manual edits are kept and choosing custom does not clear entered settings',()=>{
 const preset=applyDnsPreset(newUpstream('a'),'google-dot');const changed={...preset,tls_name:'my.example'};
 assert.equal(findDnsPreset(changed),undefined);assert.equal(selectedDnsPreset(preset,true),'custom');assert.equal(selectedDnsPreset(preset,false),'google-dot');assert.deepEqual(applyDnsPreset(changed,''),changed);assert.equal(findDnsPreset(applyDnsPreset(preset,'cloudflare-doh'))?.id,'cloudflare-doh');
});
