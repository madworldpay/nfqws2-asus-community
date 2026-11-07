import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createServer} from 'node:http';
import {fileURLToPath} from 'node:url';
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');

const directory=fileURLToPath(new URL('.',import.meta.url));
let revision='a'.repeat(64), token=0, job=null, ticks=0, running=false, fail=false;
let templates=[{id:'current',name:'Текущая стратегия'},{id:'stock',name:'Стоковая стратегия'}];
let saved={schema_version:1,mode:'split',devices:[{id:'manual-00000001',name:'TV',mac:'',addresses:['192.168.87.20']}],
  profiles:[{id:'profile-00000001',name:'TV profile',enabled:true,strategy:'stock',device_ids:['manual-00000001']}]};
const calls=[];
const runtime=()=>({available:true,configured:true,mode:job?.state==='succeeded'?'split':'common',running,
  applied_revision:job?.state==='succeeded'?revision:null,job,limits:{additional_processes:4,library:8},templates:templates.slice(2)});
const status=()=>({schema_version:1,experimental:true,applied:false,revision,draft:saved,templates,runtime:runtime(),
  discovery:{state:'available',checked_at:'now',interfaces:['br-lan'],devices:[]}});
const server=createServer(async(req,res)=>{
  try{
    if(req.url==='/index.php'){
      const chunks=[];for await(const chunk of req)chunks.push(chunk);
      const p=new URLSearchParams(Buffer.concat(chunks).toString());const cmd=p.get('cmd');calls.push({cmd,params:Object.fromEntries(p)});
      res.setHeader('Content-Type','application/json');
      const send=(value)=>res.end(JSON.stringify(value));
      if(cmd==='status'){token++;return send({csrf_token:'t'+token});}
      assert.equal(p.get('csrf_token'),'t'+token);
      if(cmd==='deviceprofilesstatus')return send(status());
      if(cmd==='deviceprofilessave'){saved=JSON.parse(p.get('draft'));revision='b'.repeat(64);return send(status());}
      if(cmd==='deviceprofilescapture'){
        templates.push({id:'saved-0000000000000001',name:p.get('name')});return send(templates.at(-1));
      }
      if(cmd==='importcatalog')return send({schema_version:1,revision:7,profiles:[{id:'example',title:'Профиль оператора',description:'Измерен на одной линии.',sha256:'c'.repeat(64)}]});
      if(cmd==='importcatalogload')return send({document:'{"type":"nfqws2_strategy"}'});
      if(cmd==='deviceprofilesimport'){
        templates.push({id:'saved-0000000000000002',name:p.get('name')});return send(templates.at(-1));
      }
      if(cmd==='deviceprofilesapply'){
        assert.equal(p.get('revision'),revision);assert.equal(p.get('consent'),'apply');assert.match(p.get('request_id'),/^[a-f0-9]{32}$/);
        job={id:'d'.repeat(32),state:'running',phase:'validating',code:null,original_code:null,recovered:null,revision};ticks=0;
        running=p.get('start_after')==='1';return send(job);
      }
      if(cmd==='deviceprofilesruntime'){
        if(job&&++ticks>=2)job={...job,state:fail?'failed':'succeeded',phase:fail?'checking':'finished',code:fail?'queue_conflict':null,original_code:fail?'queue_conflict':null,recovered:fail?true:null};
        return send(runtime());
      }
      throw new Error('unexpected '+cmd);
    }
    const name=req.url.split('/').at(-1);const types={'device-profiles-lab.html':'text/html','device-profiles-lab.js':'text/javascript','device-profiles-lab.css':'text/css'};
    if(!types[name]){res.statusCode=404;res.end();return;}
    res.setHeader('Content-Type',types[name]);res.end(await readFile(directory+name));
  }catch(error){res.statusCode=500;res.end(JSON.stringify({error:String(error)}));}
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
try{
  browser=await chromium.launch({executablePath:'/opt/google/chrome/chrome',headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
  const page=await browser.newPage({viewport:{width:390,height:844}});const errors=[];page.on('pageerror',e=>errors.push(String(e)));
  page.setDefaultTimeout(10000);
  await page.goto(`http://127.0.0.1:${server.address().port}/device-profiles-lab/device-profiles-lab.html`);
  await page.locator('#save-state').filter({hasText:'Черновик сохранён'}).waitFor();
  assert.equal(await page.locator('#apply').count(),1,'missing explicit runtime activation');
  assert.equal(await page.locator('#start-after').isChecked(),false,'former OFF stays the default');
  assert.equal(await page.locator('#apply').isEnabled(),true);
  await page.getByLabel('Название профиля',{exact:true}).fill('Local edit');
  assert.equal(await page.locator('#apply').isDisabled(),true,'unsaved editor cannot activate');
  await page.locator('#library-section summary').click();
  await page.locator('#strategy-name').fill('My snapshot');await page.locator('#capture-current').click();
  await page.locator('#notice').filter({hasText:'библиотек'}).waitFor();
  assert.equal(await page.getByLabel('Название профиля',{exact:true}).inputValue(),'Local edit','library refresh never discards editor');
  assert.equal(await page.getByRole('option',{name:'My snapshot',exact:true}).count(),1);
  await page.getByLabel('Стратегия',{exact:true}).selectOption('saved-0000000000000001');
  await page.locator('#save').click();await page.locator('#save-state').filter({hasText:'Черновик сохранён'}).waitFor();
  await page.locator('#catalog-load').click();
  await page.locator('#catalog-profile option[value="example"]').waitFor({state:'attached'});
  await page.locator('#catalog-profile').selectOption('example');
  assert.match(await page.locator('#catalog-description').textContent(),/одной линии/);
  await page.locator('#catalog-add').click();
  await page.locator('#profiles option[value="saved-0000000000000002"]').waitFor({state:'attached'});
  assert.equal(calls.filter(v=>v.cmd==='deviceprofilesimport').length,1);
  await page.locator('#start-after').check();await page.locator('#apply').click();
  await page.locator('#runtime-info').filter({hasText:'Применено'}).waitFor();
  assert.equal(calls.filter(v=>v.cmd==='deviceprofilesapply').length,1);
  assert.equal(calls.find(v=>v.cmd==='deviceprofilesapply').params.start_after,'1');
  fail=true;await page.locator('#apply').click();
  await page.locator('#job-details').filter({hasText:'queue_conflict'}).waitFor();
  assert.equal(await page.locator('#copy-error').isVisible(),true);
  assert.match(await page.locator('#job-details').textContent(),/Восстановлен/);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'mobile remains scrollable without horizontal overflow');
  assert.deepEqual(errors,[]);
  console.log('PASS: library/catalog, no lost edits, explicit saved-only apply, former OFF, detached progress, failure/copy reason, mobile.');
}finally{if(browser)await browser.close();await new Promise(r=>server.close(r));}
