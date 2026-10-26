<?php
require_once __DIR__.'/openwrt-update-guard.php';
require_once __DIR__.'/openwrt-update-manager.php';
require_once __DIR__.'/openwrt-update-snapshot.php';

/** Invoked by a native manager hook before mutation and after owned-service stop. */
final class NfqwsOpenWrtUpdateHook
{
    public function __construct(private AsusUpdateStore $store,private array $options=[]){}
    private function journal(array $ticket):array
    {
        $path=$this->options['journal']??'/tmp/nfqws2-native-package/state';AsusUpdateStore::noLinks($path);clearstatcache(true,$path);$s=@lstat($path);
        if(!$s||!is_file($path)||$s['uid']!==0||($s['mode']&0777)!==0600||$s['nlink']!==1||$s['size']>4096)throw new RuntimeException('invalid_state');
        $v=[];foreach(explode("\n",trim((string)file_get_contents($path)))as $line){if(!preg_match('/^([a-z_]+)=([^\r\n]*)$/D',$line,$m)||isset($v[$m[1]]))throw new RuntimeException('invalid_state');$v[$m[1]]=$m[2];}
        $keys=array_keys($v);sort($keys);$expected=['manager','enabled','running','web_present','web_enabled','web_running'];sort($expected);
        $m=$ticket['manager'];if($keys!==$expected||$v['manager']!==$ticket['boot_id'].':'.$m['pid'].':'.$m['start_ticks'])throw new RuntimeException('invalid_state');
        foreach(array_diff($keys,['manager'])as $key)if(!in_array($v[$key],['0','1'],true))throw new RuntimeException('invalid_state');
        $mode=$v['running']==='1'?'running':(($ticket['intent']['mode']==='waiting_for_wan'&&$v['enabled']==='1')?'waiting_for_wan':'stopped');
        return ['mode'=>$mode,'enabled'=>$v['enabled']==='1','web_enabled'=>$v['web_enabled']==='1','web_running'=>$v['web_running']==='1'];
    }
    public function run(string $action):bool
    {
        if(!in_array($action,['verify','capture','postinstall'],true))throw new RuntimeException('invalid_request');$guard=new NfqwsOpenWrtUpdateGuard($this->store);$ticket=$guard->ticket();
        if($ticket===null||$ticket['phase']==='finished')return false;
        if(!AsusUpdateLifecycle::alive($ticket['worker'])&&!$guard->managerAlive($ticket)){if(NfqwsOpenWrtManualContext::authorize())return false;$f=$guard->mutationLease();flock($f,LOCK_UN);fclose($f);return false;}
        $end=AsusUpdateStore::uptime()+2;
        do{
            $ticket=$guard->context($ticket['id']);
            $authorized=$guard->authorize('hook-prerm');
            if($authorized&&is_file($this->options['journal']??'/tmp/nfqws2-native-package/state'))break;
            if(!$authorized&&$ticket['manager']!==null||AsusUpdateStore::uptime()>=$end)throw new RuntimeException('busy');usleep(10000);
        }while(true);
        $id=$ticket['id'];$base='operations/'.$id;
        $preflight=json_decode($this->store->readFile($base.'/native-preflight.json')??'',true,32,JSON_THROW_ON_ERROR);
        if(!is_array($preflight['installed']??null))throw new RuntimeException('invalid_state');
        $current=NfqwsOpenWrtUpdateManager::installed(['format'=>$ticket['format']],true);$expected=$preflight['installed'];unset($expected['nfqws2-native']);ksort($expected);
        if($current!==$expected)throw new RuntimeException('dependency_change');
        $ticket['intent']=$this->journal($ticket);$this->store->writeFile('native-transaction.json',json_encode($ticket,JSON_THROW_ON_ERROR));$this->store->update($id,['intent'=>$ticket['intent']]);
        if($action==='postinstall'){
            $raw=$this->store->readFile($base.'/quiesced.json',1024);
            if($raw===null||json_decode($raw,true)!==['captured'=>true])throw new RuntimeException('invalid_state');
        }
        if($action==='capture'){
            $backup=$this->store->path($base.'/backup');$root=$this->options['root']??'/';
            if(!is_dir($backup))NfqwsOpenWrtUpdateSnapshot::capture($backup,$root);else NfqwsOpenWrtUpdateSnapshot::verify($backup,$root);
            $this->store->writeFile($base.'/quiesced.json',json_encode(['captured'=>true],JSON_THROW_ON_ERROR));
        }
        return true;
    }
}
