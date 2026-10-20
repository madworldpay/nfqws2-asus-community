import assert from 'node:assert/strict';
let p;try{p=await import('../webui/web/src/api/dpiPresentation.ts');}catch{p={};}
assert.equal(typeof p.presentDpiNative,'function','native tables missing');
const value={type:'nfqws2_dpi_native',groups:[{group:2,document:{results:{domain_inspection:[{domain:'<private>',resolved:'127.0.0.1',http:'ok',http_detail:'http_200',tls12:'ok',tls12_detail:'elapsed_12ms',tls13:'timeout',tls13_detail:'tcp_syn_timeout',quic:'timeout',quic_detail:'quic_timeout'}]}}},{group:3,document:{results:{tcp16:[{id:'X',provider:'Y',status:'timeout',detail:'read_timeout_word_at_24kb'}]}}}]};
const models=p.presentDpiNative(value,'ru');assert.equal(models.length,2);assert.equal(models[0].rows[0][0].text,'<private>');assert.match(JSON.stringify(models),/24/);assert.match(JSON.stringify(models),/200/);assert.match(JSON.stringify(models),/quic_timeout/);assert.equal(models[0].rows[0][2].tone,'success');
console.log('PASS native domain/TCP columns keep details and render private strings as text');

value.groups[0].document.results.domain_inspection[0].quic='quic_ok';
assert.equal(p.presentDpiNative(value,'ru')[0].rows[0].at(-1).tone,'success','successful QUIC must be positive');
