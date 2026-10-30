import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';
const d=await mkdtemp(join(tmpdir(),'auth-error-'));
try {
 const source=fileURLToPath(new URL('../webui/web/src/utils/authError.ts',import.meta.url));
 await build({entryPoints:[source],outfile:join(d,'util.mjs'),bundle:true,platform:'node',format:'esm',logLevel:'silent'});
 const {isAuthUnconfigured}=await import(pathToFileURL(join(d,'util.mjs')));
 for(const error of ['',null,undefined,0,false,'auth_unconfigured',[],{}, {error:null}]) assert.equal(isAuthUnconfigured(error),false);
 assert.equal(isAuthUnconfigured({error:'auth_unconfigured'}),true);
 console.log('PASS empty HTTP 401 body cannot crash the login screen');
} finally {await rm(d,{recursive:true,force:true});}
