"""Exercise the PHP/native handoff with real owners and sockets, no host DNS changes."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_dpi_normalize import ROOT,PHP,PUBLIC
from test_smartdns_profile import profile


class SmartDnsNativeConnectionTests(unittest.TestCase):
    def exercise(self,mode='ready'):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);native=root/'jffs/nfqws2-asus-smartdns';library=root/'lib'
            for folder in [root/'jffs',library,root/'scripts',root/'app',root/'app/updates',root/'engine',root/'engine'/('a'*64),root/'engine'/('a'*64)/'lib']:
                folder.mkdir(mode=0o700)
            (root/'app/updates/apply.lock').touch(mode=0o600)
            (root/'dns-generation').write_text('1\n')
            (root/'uptime').write_text('100.000 0\n')
            if mode=='occupied_run':
                (root/'app/smartdns').mkdir(mode=0o700);(root/'app/smartdns/jobs').mkdir(mode=0o700)
                (root/'app/smartdns/jobs'/('c'*32)).mkdir(mode=0o700)
                (root/'app/smartdns/jobs'/('c'*32)/'unrelated').write_text('untouched')
            hook=root/'scripts/dnsmasq.postconf';hook.write_text('#!/bin/sh\n# foreign configuration\n');hook.chmod(0o751)
            original=hook.read_bytes()
            code=root/'engine.c';code.write_text('''#include <arpa/inet.h>
#include <sys/socket.h>
#include <unistd.h>
int main(void){struct sockaddr_in a={.sin_family=AF_INET,.sin_port=htons(6054),.sin_addr.s_addr=htonl(0x7f000001)};
int u=socket(AF_INET,SOCK_DGRAM,0),t=socket(AF_INET,SOCK_STREAM,0),one=1;
setsockopt(t,SOL_SOCKET,SO_REUSEADDR,&one,sizeof(one));
if(u<0||t<0||bind(u,(void*)&a,sizeof(a))||bind(t,(void*)&a,sizeof(a))||listen(t,2))return 2;
for(;;)sleep(1);}
''')
            binary=root/'engine'/('a'*64)/'smartdns'
            subprocess.run(['gcc',str(code),'-o',str(binary)],capture_output=True,check=True);binary.chmod(0o700)
            (root/'engine/current').symlink_to('a'*64)
            engine_alias=root/'engine'
            opt_alias=root/'app'
            if mode=='opt_alias':
                engine_alias=root/'engine-alias';engine_alias.symlink_to(root/'engine')
                opt_alias=root/'opt-alias';opt_alias.symlink_to(root/'app')
            artifact={'sha256':'a'*64,'version':'fixture','files':{'smartdns':{'size':binary.stat().st_size,'sha256':hashlib.sha256(binary.read_bytes()).hexdigest()}},'links':{}}
            (root/'artifact.json').write_text(json.dumps(artifact))
            source=ROOT/'asus/smartdns'
            for name in ['native-state.sh','native-common.sh','primary-dns.sh','recovery.sh','lifecycle.sh','runtime.sh','forwarding.awk','hook-edit.awk']:
                body=(source/name).read_text().replace('/jffs/nfqws2-asus-smartdns',str(native)).replace('/jffs/scripts',str(root/'scripts')).replace('/opt/var/lib/nfqws2-asus/updates',str(root/'app/updates')).replace('/opt/etc/nfqws-asus-web',str(opt_alias)).replace('/opt/lib/nfqws2-asus/smartdns-engine',str(engine_alias)).replace('/opt/lib/nfqws2-asus/smartdns',str(library)).replace('/tmp/etc/dnsmasq.conf',str(root/'dnsmasq.conf')).replace('/sbin/service',str(root/'service')).replace('sd_owner=0','sd_owner='+str(os.getuid()))
                if name=='native-common.sh':body+='\nsd_primary_identity() { printf "123 %s\\n" "$(cat "'+str(root/'dns-generation')+'")"; }\n'
                if mode=='browser_loss':body=body.replace('/proc/uptime',str(root/'uptime'))
                (library/name).write_text(body);(library/name).chmod(0o700)
            probe=('#!/bin/sh\n[ ! -f "'+str(root/'probe-fail')+'" ] || exit 2\nprintf \'{"ok":true,"rcode":0,"truncated":false,"answers":["192.0.2.1"]}\\n\'\n').encode()
            (library/'dns-probe').write_bytes(probe);(library/'dns-probe').chmod(0o700)
            (library/'tools.json').write_text(json.dumps({'schema_version':1,'dns_probe_sha256':hashlib.sha256(probe).hexdigest()}));(library/'tools.json').chmod(0o600)
            syntax=root/'syntax';syntax.write_text('#!/bin/sh\nexit 0\n');syntax.chmod(0o700)
            path=library/'lifecycle.sh';path.write_text(path.read_text().replace('/usr/sbin/dnsmasq',str(syntax)));path.chmod(0o700)
            service=root/'service';service.write_text('#!/bin/sh\nprintf "interface=lo\\nserver=9.9.9.9\\n" > "'+str(root/'dnsmasq.conf')+'"\nchmod 600 "'+str(root/'dnsmasq.conf')+'"\nif /bin/busybox grep -q "NFQWS2 SMARTDNS MANAGED" "'+str(hook)+'";then /bin/sh "'+str(native/'lifecycle.sh')+'" postconf "'+str(root/'dnsmasq.conf')+'" || exit 2;fi\nvalue=$(cat "'+str(root/'dns-generation')+'")\nprintf "%s\\n" "$((value+1))" > "'+str(root/'dns-generation')+'"\n');service.chmod(0o700)
            holder=root/'holder.sh'
            holder.write_text('#!/bin/sh\nexec 6>>"$1"\n/usr/bin/flock '+('-s' if mode=='journal_contention' else '-x')+' 6 || exit 2\nprintf locked > "$2"\nsleep '+('0.25' if mode=='journal_contention' else '1.5')+'\n');holder.chmod(0o700)
            public=PUBLIC
            if mode in ['native_detacher','browser_loss']:
                public=root/'public';public.mkdir()
                for source in PUBLIC.glob('*.php'):
                    text=source.read_text()
                    if source.name=='dpi-runtime.php':text=text.replace("BUSYBOX='/opt/libexec/nfqws2-asus/busybox'","BUSYBOX='/bin/busybox'")
                    (public/source.name).write_text(text)
            php=r'''require $argv[1].'/smartdns-native.php';require $argv[1].'/smartdns-lifecycle.php';$root=$argv[2];$owner=(int)$argv[3];$mode=$argv[4];umask(0077);
            $clock=fn()=>$mode==='browser_loss'?(float)explode(' ',file_get_contents($root.'/uptime'))[0]:(float)explode(' ',file_get_contents('/proc/uptime'))[0];
            $store=new AsusSmartDnsStore($root.'/app/smartdns',$owner,['uptime'=>$clock]);$installer=new AsusSmartDnsInstaller($root.'/engine',$owner,json_decode(file_get_contents($root.'/artifact.json'),true));
            $process=null;$lockprocess=null;$validationHolder=null;$mode=$argv[4];$deps=['owner'=>$owner,'primary_dns'=>fn()=>true,'recovery_storage'=>fn()=>true,'baseline'=>function()use($root){$hook=file_get_contents($root.'/scripts/dnsmasq.postconf');return ['hash'=>hash('sha256',$hook),'snapshot'=>['hook'=>['state'=>'available','value'=>$hook,'mode'=>0751],'config'=>['state'=>'available','value'=>"server=9.9.9.9\n"]],'conflicts'=>[]];},
            'launch'=>function($id)use($root,&$process,&$lockprocess,$mode){if($mode==='cleanup_failed'){file_put_contents($root.'/probe-fail','');throw new RuntimeException('launch_failed');}
              $process=proc_open(['/bin/sh',$root.'/jffs/nfqws2-asus-smartdns/recovery.sh','guard',$id],[0=>['file','/dev/null','r'],1=>['file','/dev/null','a'],2=>['file','/dev/null','a']],$pipes);if(!is_resource($process))throw new RuntimeException('launch_failed');
              if(in_array($mode,['contention','journal_contention'],true)){for($i=0;$i<300&&!is_file($root.'/jffs/nfqws2-asus-smartdns/ready');$i++)usleep(10000);
                $lockfile=$mode==='journal_contention'?$root.'/app/smartdns/state.lock':$root.'/jffs/nfqws2-asus-smartdns/state.lock';
                $lockprocess=proc_open(['/bin/sh',$root.'/holder.sh',$lockfile,$root.'/locked'],[0=>['file','/dev/null','r'],1=>['file','/dev/null','a'],2=>['file','/dev/null','a']],$unused);
                for($i=0;$i<100&&!is_file($root.'/locked');$i++)usleep(10000);
              }}];
            $paths=['native'=>$root.'/jffs/nfqws2-asus-smartdns','library'=>$root.'/lib','hook'=>$root.'/scripts/dnsmasq.postconf'];
            $foreignsh=null;if(in_array($mode,['native_detacher','browser_loss'],true))unset($deps['launch']);
            if($mode==='native_detacher')$foreignsh=proc_open(['/bin/sh','-c','while :; do sleep 1; done'],[0=>['file','/dev/null','r'],1=>['file','/dev/null','a'],2=>['file','/dev/null','a']],$unused);
            $backend=new AsusSmartDnsNativeBackend($store,$installer,$paths,$deps);
            try{$profile=json_decode(stream_get_contents(STDIN),true);$hash=$store->saveDraft($profile);$base=($deps['baseline'])()['hash'];$id=str_repeat('c',32);$preview=str_repeat('b',32);
              $store->savePreview(['id'=>$preview,'profile_hash'=>$hash,'baseline_hash'=>$base,'expires_uptime'=>$clock()+600]);
              $connection=new AsusSmartDnsConnection($store,$backend->dependencies()+['uptime'=>$clock]);$states=[];
              $states[]=$connection->apply($id,$preview,$hash,$base);$native=$backend->state();
              if($mode==='cleanup_failed'){unlink($root.'/probe-fail');$states[]=$connection->rollback($id);}
              elseif(str_starts_with($mode,'upgrade_resume')){
                $states[]=$connection->confirm($id);$life=new AsusSmartDnsLifecycle($store,$backend,$installer,['jobs_deps'=>['owner'=>$owner],'validate'=>function($validation,$hash)use($store,$backend,$mode,$root,&$validationHolder){
                  $base=$backend->baseline()['hash'];$store->beginValidation($validation,$hash,$base);
                  if($mode==='upgrade_resume_edited'){$p=$store->draft();$p['upstreams'][0]['label']='new concurrent edit';$store->saveDraft($p);$store->transition($validation,['validating'],['state'=>'failed','code'=>'stale_draft']);return;}
                  if($mode==='upgrade_resume_handoff'){
                    $run=$root.'/app/smartdns/jobs/'.$validation;mkdir($run,0700);
                    $holder=$root.'/validation-holder.sh';file_put_contents($holder,"#!/bin/sh\nexec 9>>\"\$1\"\n/usr/bin/flock -x 9\nprintf ready >\"\$2\"\nsleep 3\n");chmod($holder,0700);
                    $validationHolder=proc_open(['/bin/sh',$holder,$root.'/app/smartdns/config.lock',$root.'/validation-ready'],[0=>['file','/dev/null','r'],1=>['file','/dev/null','a'],2=>['file','/dev/null','a']],$none);
                    for($n=0;$n<100&&!is_file($root.'/validation-ready');$n++)usleep(10000);
                    $pid=proc_get_status($validationHolder)['pid'];$identity=AsusDpiRuntime::identity($pid);
                    file_put_contents($run.'/guard',$pid.' '.$identity['starttime'].' '.$identity['boot_id'].' 999999999.000'."\n");chmod($run.'/guard',0600);
                  }
                  $preview=['id'=>str_repeat('f',32),'profile_hash'=>$hash,'baseline_hash'=>$base,'expires_uptime'=>(float)explode(' ',file_get_contents('/proc/uptime'))[0]+600];$store->savePreview($preview);$store->transition($validation,['validating'],['state'=>'preview_ready','preview_id'=>$preview['id']]);
                }]);
                $states[]=$life->stop('upgrade');$other=$profile;$other['upstreams'][0]['label']='prepared next profile';if($mode==='upgrade_resume_draft')$store->saveDraft($other);
                $states[]=$life->resume();$resumedHash=$store->active()['profile_hash']??null;$draftLabel=$store->draft()['upstreams'][0]['label'];
                if(in_array($mode,['upgrade_resume','upgrade_resume_handoff'],true))$states[]=$connection->rollback($store->transaction()['request_id']);
              }
              elseif(!in_array($mode,['occupied_run','browser_loss'],true)){$states[]=$connection->confirm($id);$states[]=$connection->rollback($id);}
              echo json_encode(['states'=>$states,'runtime_pid'=>$native['runtime_pid'],'native'=>$backend->state(),'active'=>$store->active(),'resumed_hash'=>$resumedHash??null,'draft_label'=>$draftLabel??null]);
            }catch(Throwable $e){echo json_encode(['error'=>$e->getMessage(),'states'=>$states??[],'job'=>$store->status(),'native'=>$backend->state(),'log'=>@file_get_contents($root.'/jffs/nfqws2-asus-smartdns/recovery.log'),'events'=>@file_get_contents($root.'/dnsmasq.conf')]);}
            finally{if($mode!=='browser_loss'){try{$s=$backend->state();if($s!==null&&$s['phase']!=='rolled_back')$backend->restore(['request_id'=>$s['request_id'],'profile_hash'=>$s['profile_hash']],[]);}catch(Throwable $e){}}
              if(is_resource($foreignsh)){proc_terminate($foreignsh,15);proc_close($foreignsh);}if(is_resource($lockprocess))proc_close($lockprocess);if(is_resource($process)){proc_terminate($process,15);usleep(1500000);$s=proc_get_status($process);if($s['running'])proc_terminate($process,9);proc_close($process);}}'''
            p=subprocess.run([PHP,'-n','-r',php,str(public),str(root),str(os.getuid()),mode],input=json.dumps(profile()),capture_output=True,text=True,timeout=30)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'');out=json.loads(p.stdout)
            self.assertNotIn('error',out)
            if mode=='browser_loss':
                import fcntl,time
                def wait_for(predicate):
                    end=time.monotonic()+8
                    while time.monotonic()<end:
                        if predicate():return
                        time.sleep(.03)
                    self.fail('detached deadline event not observed')
                try:
                    self.assertEqual([s['state'] for s in out['states']],['awaiting_confirmation'])
                    self.assertTrue(Path('/proc/'+out['runtime_pid']).exists())
                    with (root/'app/updates/apply.lock').open('r+') as lease:
                        with self.assertRaises(BlockingIOError):fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    (root/'uptime').write_text('221.000 0\n')
                    wait_for(lambda:'phase\trolled_back\n' in (native/'state').read_text())
                    wait_for(lambda:not Path('/proc/'+out['runtime_pid']).exists())
                    self.assertEqual(hook.read_bytes(),original)
                    self.assertNotIn('127.0.0.1#6054',(root/'dnsmasq.conf').read_text())
                finally:
                    subprocess.run(['/bin/sh',str(native/'recovery.sh'),'rollback','c'*32],capture_output=True,timeout=20)
                return
            expected={'occupied_run':['failed'],'cleanup_failed':['conflict','rolled_back'],'upgrade_resume':['awaiting_confirmation','confirmed','rolled_back','confirmed','rolled_back'],'upgrade_resume_handoff':['awaiting_confirmation','confirmed','rolled_back','confirmed','rolled_back'],'upgrade_resume_edited':['awaiting_confirmation','confirmed','rolled_back','failed'],'upgrade_resume_draft':['awaiting_confirmation','confirmed','rolled_back','action_required']}.get(mode,['awaiting_confirmation','confirmed','rolled_back'])
            self.assertEqual([x['state'] for x in out['states']],expected)
            self.assertEqual(out['native']['phase'],'rolled_back');self.assertIsNone(out['active'])
            if mode=='upgrade_resume':self.assertIsNotNone(out['resumed_hash']);self.assertEqual(out['draft_label'],'main')
            if mode=='upgrade_resume_draft':self.assertIsNone(out['resumed_hash']);self.assertEqual(out['draft_label'],'prepared next profile')
            if mode=='upgrade_resume_edited':self.assertEqual(out['draft_label'],'new concurrent edit')
            self.assertEqual(hook.read_bytes(),original)
            self.assertNotIn('127.0.0.1#6054',(root/'dnsmasq.conf').read_text())
            if out['runtime_pid']!='0':self.assertFalse(Path('/proc/'+out['runtime_pid']).exists())
            if mode=='occupied_run':self.assertEqual((root/'app/smartdns/jobs'/('c'*32)/'unrelated').read_text(),'untouched')

    def test_resume_waits_for_validator_releasing_the_config_lease(self):self.exercise('upgrade_resume_handoff')

    def test_resume_preserves_a_different_draft_without_temporarily_replacing_it(self):self.exercise('upgrade_resume_draft')
    def test_upgrade_resumes_only_the_confirmed_profile_and_preserves_next_draft(self):self.exercise('upgrade_resume')
    def test_resume_never_overwrites_an_edit_arriving_during_validation(self):self.exercise('upgrade_resume_edited')
    def test_native_guard_apply_confirm_and_verified_restore(self):self.exercise()
    def test_native_state_lock_waits_without_replaying_the_mutation(self):self.exercise('contention')
    def test_journal_reader_does_not_abort_a_started_native_guard(self):self.exercise('journal_contention')
    def test_default_detacher_does_not_match_unrelated_shell_processes(self):self.exercise('native_detacher')
    def test_failure_before_launch_still_releases_prepared_native_transaction(self):self.exercise('occupied_run')
    def test_unresolved_partial_start_is_conflict_and_can_be_restored_later(self):self.exercise('cleanup_failed')
    def test_entware_alias_uses_the_canonical_engine_identity(self):self.exercise('opt_alias')
    def test_cgi_exit_does_not_release_the_guard_or_cancel_native_deadline(self):self.exercise('browser_loss')


if __name__=='__main__':unittest.main()
