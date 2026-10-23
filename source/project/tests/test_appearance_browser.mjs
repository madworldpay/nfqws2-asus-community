import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {fileURLToPath} from 'node:url';
import {build} from '../webui/web/node_modules/esbuild/lib/main.js';
const {chromium}=await import(process.env.NFQWS_PLAYWRIGHT_MODULE||'playwright');
const web=fileURLToPath(new URL('../webui/web/',import.meta.url));
const result=await build({stdin:{resolveDir:web,loader:'tsx',contents:`import React from 'react';import {createRoot} from 'react-dom/client';import {Layout} from './src/components/Layout';import {useTheme} from '@mui/material';import {useAppearanceStore} from './src/store/useAppearanceStore';function Probe(){return <div id="probe" data-mode={useTheme().palette.mode} data-appearance={useAppearanceStore().appearance}/>};createRoot(document.getElementById('root')).render(<Layout><Probe/></Layout>);`},bundle:true,platform:'browser',format:'iife',write:false,jsx:'automatic',logLevel:'silent',tsconfig:web+'/tsconfig.app.json'});
let browser,server;
try{
 server=createServer((req,res)=>{res.setHeader('Content-Type',req.url==='/fixture.js'?'text/javascript':'text/html');res.end(req.url==='/fixture.js'?result.outputFiles[0].contents:'<!doctype html><html><body><div id="root"></div><script src="/fixture.js"></script></body></html>');});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 browser=await chromium.launch({headless:true,...(process.env.NFQWS_CHROMIUM_EXECUTABLE?{executablePath:process.env.NFQWS_CHROMIUM_EXECUTABLE}:{})});
 for(const [appearance,mode,expected] of [[null,null,'dark'],['classic','light','light'],['classic','dark','dark'],['rabbit','dark','dark']]){
  const page=await browser.newPage({colorScheme:'light'});
  await page.addInitScript(({appearance,mode})=>{localStorage.clear();if(appearance)localStorage.setItem('nfqws2-appearance',appearance);if(mode)localStorage.setItem('theme',mode);},{appearance,mode});
  await page.goto('http://127.0.0.1:'+server.address().port);
  await page.waitForFunction(expected=>document.querySelector('#probe')?.getAttribute('data-mode')===expected,expected,{timeout:3000});
  assert.equal(await page.locator('#probe').getAttribute('data-appearance'),appearance??'rabbit');
  await page.close();
 }
 console.log('PASS real theme layout: first visit dark Rabbit Hole, saved classic light/dark and Rabbit Hole');
}finally{await browser?.close();if(server)await new Promise(r=>server.close(r));}
