import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {build} from '../webui/web/node_modules/esbuild/lib/main.js';
const dir=await mkdtemp(join(tmpdir(),'import-paths-'));
try {
  const root=fileURLToPath(new URL('../webui/web/src/',import.meta.url));
  await build({entryPoints:[join(root,'api/importPaths.ts')],outfile:join(dir,'paths.mjs'),bundle:true,alias:{'@':root},platform:'node',format:'esm',logLevel:'silent'});
  const {displayImportValue,encodeImportValue,unresolvedImportAliases,formatImportArguments}=await import(pathToFileURL(join(dir,'paths.mjs')));
  const files=[
    {id:'blob',kind:'blobs',name:'tls_clienthello.bin',sha256:'a'.repeat(64),aliases:['RESOURCE_1']},
    {id:'lua',kind:'lua',name:'zapret-lib.lua',sha256:'b'.repeat(64),aliases:['RESOURCE_2']},
    {id:'list',kind:'lists',name:'user.list',sha256:'c'.repeat(64),aliases:['RESOURCE_10']},
  ];
  const canonical='--blob=tls:@RESOURCE_1 --lua-init=RESOURCE_2 --hostlist=RESOURCE_10 --filter-tcp=443';
  const readable='--blob=tls:@/opt/etc/nfqws2/blobs/tls_clienthello.bin --lua-init=@/opt/etc/nfqws2/lua/zapret-lib.lua --hostlist=/opt/etc/nfqws2/lists/user.list --filter-tcp=443';
  assert.equal(displayImportValue(canonical,files),readable);
  assert.equal(displayImportValue(encodeImportValue(readable,files),files),readable);
  const edited=readable.replace('443','80,443');
  assert.equal(displayImportValue(encodeImportValue(edited,files),files),edited);
  assert.match(encodeImportValue(edited,files),/--hostlist=RESOURCE_10/);
  assert.equal(displayImportValue('--lua-init RESOURCE_2 --blob tls:RESOURCE_1',files),'--lua-init @/opt/etc/nfqws2/lua/zapret-lib.lua --blob tls:@/opt/etc/nfqws2/blobs/tls_clienthello.bin');
  assert.equal(displayImportValue('PREFIX_RESOURCE_1 RESOURCE_100 RESOURCE_99',files),'PREFIX_RESOURCE_1 RESOURCE_100 RESOURCE_99');
  assert.deepEqual(unresolvedImportAliases('RESOURCE_1 RESOURCE_99 RESOURCE_99',files),['RESOURCE_99']);
  assert.equal(encodeImportValue('--hostlist=/tmp/opt/etc/nfqws2/lists/user.list --other=/opt/etc/nfqws2/lists/user.list.other',files),'--hostlist=/tmp/opt/etc/nfqws2/lists/user.list --other=/opt/etc/nfqws2/lists/user.list.other');
  const conflict=[...files,{...files[2],id:'other',sha256:'d'.repeat(64),aliases:['RESOURCE_11']}];
  assert.equal(displayImportValue('RESOURCE_10 RESOURCE_11',conflict),'RESOURCE_10 RESOURCE_11');
  assert.equal(encodeImportValue('/opt/etc/nfqws2/lists/user.list',conflict),'/opt/etc/nfqws2/lists/user.list');
  assert.deepEqual(unresolvedImportAliases('RESOURCE_10 RESOURCE_11',conflict),['RESOURCE_10','RESOURCE_11']);
  assert.equal(displayImportValue('RESOURCE_7',[{kind:'lists',name:'bad name.list',aliases:['RESOURCE_7']}]),'RESOURCE_7');
  assert.equal(formatImportArguments('--filter-tcp=443 --hostlist=/opt/etc/nfqws2/lists/user.list'), '--filter-tcp=443\n--hostlist=/opt/etc/nfqws2/lists/user.list');
  assert.equal(formatImportArguments('--lua-init @/opt/etc/nfqws2/lua/zapret-lib.lua --blob tls:@/opt/etc/nfqws2/blobs/hello.bin'), '--lua-init @/opt/etc/nfqws2/lua/zapret-lib.lua\n--blob tls:@/opt/etc/nfqws2/blobs/hello.bin');
  assert.equal(formatImportArguments(`--one='keep --inside=1' --two="keep --inside=2"`), `--one='keep --inside=1'\n--two="keep --inside=2"`);
  assert.equal(formatImportArguments('--a=1\n  --b=2'), '--a=1\n  --b=2');
  console.log('PASS readable import paths, edit round-trip preserving resource identities, exact boundaries and unresolved/conflicting files');
} finally {await rm(dir,{recursive:true,force:true});}
