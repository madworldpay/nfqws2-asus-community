<?php
/** Exact production service/reset bodies; guard and service are explicit doubles. */
final class ServiceAliasDiagnosticsDouble
{
    public static function run(array $argv,int $seconds):array
    {
        $running=is_file('/opt/service-double-running');
        return ['status'=>0,'output'=>[json_encode(['process_running'=>$running,'nfqueue'=>['state'=>$running?'bound':'unbound']])]];
    }
}
function fixtureServiceAlias($runtime,$store,$config,$entry,string $mode="alias_service"):array
{
    $body='';
    foreach(['service','resetAuto']as $method){
        $m=new ReflectionMethod(NfqwsStrategyPickerRuntime::class,$method);
        $lines=file($m->getFileName());
        $body.=str_replace(['private function '.$method,'NfqwsPlatform::run'],['public function '.$method,'ServiceAliasDiagnosticsDouble::run'],
            implode('',array_slice($lines,$m->getStartLine()-1,$m->getEndLine()-$m->getStartLine()+1)));
    }
    eval('final class ServiceAliasFixture {
        public function __construct(private NfqwsStrategyPickerRuntime $runtime,private NfqwsStrategyPickerState $store,private NfqwsStrategyPickerConfig $config,private string $auto){}
        public function __call($name,$args){return (new ReflectionMethod($this->runtime,$name))->invoke($this->runtime,...$args);}
        private function actor($role,$id,&$pin=null){$pin=["component_double"=>true];return NfqwsStrategyPickerRuntime::identity(getmypid());}
        private function running():bool{return is_file("/opt/service-double-running");}
        private function actuator($argv,$seconds,$input=null,$check=null):array{
            $check();$action=$argv[count($argv)-1];
            if($action==="start"){file_put_contents($this->auto,"learned.example\n",FILE_APPEND);file_put_contents("/opt/service-double-running","1");}
            elseif($action==="stop"){@unlink("/opt/service-double-running");}
            else throw new RuntimeException("unexpected_service_double_action");
            $check();return ["status"=>0,"output"=>[]];
        }
    '.$body.'}');
    $id=$store->read()['id'];$auto=NfqwsDeviceProfilesPaths::readPath('/opt/etc/nfqws2/strategy-picker/'.$id.'/'.$entry['id'].'/lists/auto.list');
    $fixture=new ServiceAliasFixture($runtime,$store,$config,$auto);
    $fixture->resetAuto($entry);
    $config->replace((new ReflectionMethod($runtime,'candidate'))->invoke($runtime,$entry));
    $fixture->service('start');
    $out=['trial_after_start'=>$store->read()['engine_trial']??null];
    $fixture->service('stop');clearstatcache(true,$auto);
    $out['stopped_observation']=$store->read()['mutable_resources'][$entry['id']]['lists/auto.list'];
    $out['actual_stopped']=['identity'=>array_intersect_key(lstat($auto),array_flip(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime'])),'sha256'=>hash_file('sha256',$auto)];
    $out['frozen_seed']=NfqwsStrategyPickerResources::snapshotMutable($entry,dirname(dirname($auto)),0,$store);
    $fixture->resetAuto($entry);$out['next_recipe_auto']=file_get_contents($auto);
    $out['trial_after_stop']=$store->read()['engine_trial']??null;
    $config->restore();$out['restored']=$store->read()['restored'];
    $j=$store->read();$j['state']='cancelled';$j['restored']=true;
    $private=NfqwsDeviceProfilesPaths::readPath($store->root.'/job-'.$j['id']);$meta=$private.'/library/'.$entry['id'].'.json';$metaBefore=hash_file('sha256',$meta);
    if($mode!=='alias_service'){
        unlink(dirname($auto).'/google.list');
        $j['actuator_intent']=['kind'=>'picker-stage-retirement-v1','job'=>$j['id'],'profiles'=>[$entry['id']]];
        $j['actuator_attention']=['kind'=>in_array($mode,['alias_retirement','alias_retirement_current'],true)?'picker-stage-retirement-uncertain':'other-operation','job'=>$j['id']];
    }
    if($mode==='alias_retirement_current'){
        $path=NfqwsPlatform::settings()['config'].'/nfqws2.conf';$raw=file_get_contents($path);rename($path,dirname($path).'/before-next-config');file_put_contents($path,$raw);chmod($path,0664);
        file_put_contents(NfqwsPlatform::settings()['config'].'/lists/google.list',"current.example\n");
        clearstatcache(true,$path);$out['current_input_before']=['sha256'=>hash_file('sha256',$path),'metadata'=>array_intersect_key(lstat($path),array_flip(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime']))];
    }
    $store->write($j);$out['next_error']=null;
    try{(new ReflectionMethod($runtime,'clearPrevious'))->invoke($runtime,$j);}catch(Throwable $e){$out['next_error']=$e->getMessage();}
    $out['cancelled_copies_retained']=is_file($auto);$out['metadata_preserved']=is_file($meta)&&hash_file('sha256',$meta)===$metaBefore;
    $out['journal_preserved']=$store->read()===$j;
    $archive=new NfqwsStrategyPickerState($private,$store->owner());$previous=$archive->read('state.json');
    $out['attention_preserved_in_archive']=$previous!==null&&($previous['actuator_attention']??null)===($j['actuator_attention']??null);
    if($out['next_error']===null){$next=$config->snapshot(false);$out['new_job_created']=$next['id']!==$j['id'];$out['new_original_sha256']=$next['original_sha256'];}
    if($mode==='alias_retirement_current'){clearstatcache(true,$path);$out['current_input_after']=['sha256'=>hash_file('sha256',$path),'metadata'=>array_intersect_key(lstat($path),array_flip(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime']))];}
    $out['service_guard_diagnostics_are_doubles']=true;
    return $out;
}
