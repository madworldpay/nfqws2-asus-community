import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';
const dir = await mkdtemp(join(tmpdir(), 'nfqws-quotes-'));
try {
  const root = fileURLToPath(new URL('../webui/web/src/', import.meta.url));
  await build({entryPoints:[join(root,'utils/quoteDiagnostics.ts')],outfile:join(dir,'quotes.mjs'),bundle:true,platform:'node',format:'esm',logLevel:'silent'});
  const { findUnclosedQuotes } = await import(pathToFileURL(join(dir,'quotes.mjs')));
  const valid = [
    'A="--one=1\n--two=2"\nB=0\n',
    "A='one\n\"two\"'\n",
    '# This isn\'t an opening " quote\nA="ok" # nor is this \' quote\n',
    'A="a\\\"b"\nB="c\\\\"\n',
    "A='one\\'\n",
    'A="$(printf \'%s\' "a b")"\n',
    'A="$(printf \'%s\' "$(printf \'%s\' x)")"\n',
    "cat <<'END'\ntext with unmatched \" and ' quotes\nEND\nA=ok\n",
    'cat <<-END\n\t"text\n\tEND\nA=ok\n',
    "A=$'one\\\'two'\n",
    'A=a#b\nB="ok"\n',
  ];
  for (const source of valid) {
    const shell=spawnSync('/bin/bash',['-n'],{input:source,encoding:'utf8'});
    assert.equal(shell.status,0,shell.stderr+'\n'+source);
    assert.deepEqual(findUnclosedQuotes(source),[],source);
  }
  for (const quote of ['"', "'"]) {
    const source='A=1\nNFQWS_ARGS='+quote+'--one=1\n--two=2\n';
    const [issue]=findUnclosedQuotes(source);
    assert.equal(issue.quote,quote);assert.equal(issue.line,2);assert.equal(issue.column,12);
    assert.equal(source[issue.from],quote);assert.equal(issue.to,issue.from+1);
  }
  assert.equal(findUnclosedQuotes('--one="value --two=1','arg')[0].from,6);
  assert.deepEqual(findUnclosedQuotes('--one="keep --inside=1" --two=2','arg'),[]);
  assert.deepEqual(findUnclosedQuotes('then "balanced"'),[],'do not claim to validate full shell syntax');
  console.log('PASS quote diagnostics: opener positions, multiline, comments, escapes, command substitutions and here-documents');
} finally {await rm(dir,{recursive:true,force:true});}
