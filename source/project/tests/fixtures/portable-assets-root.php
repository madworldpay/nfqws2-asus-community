<?php
/** Offline ROOT transaction fixture. No service, DNS or network calls. */
umask(0022);
$child=($argv[1]??'')==='child';$platform=$child?($argv[2]??''):($argv[1]??'');
if(!in_array($platform,['asus-entware','openwrt'],true))throw new RuntimeException('fixture_platform');
$web=$platform==='openwrt'?'/usr/share/nfqws2-web':'/opt/share/nfqws-asus-web';
if(!$child){
    if(!is_dir($web))mkdir($web,0755,true);
    foreach(glob('/fixture-web/*.php') as $path){copy($path,$web.'/'.basename($path));chmod($web.'/'.basename($path),0644);}
    foreach(glob('/fixture-profiles/device-profiles-*.php') as $path){copy($path,$web.'/'.basename($path));chmod($web.'/'.basename($path),0644);}
    if($platform==='openwrt'){file_put_contents($web.'/platform-profile.json',json_encode(['schema_version'=>1,'platform'=>$platform]));chmod($web.'/platform-profile.json',0644);}
}
require $web.'/import-transaction.php';
if(!$child){
    $share=NfqwsPlatform::settings()['share'];if(!is_dir($share))mkdir($share,0755,true);
    foreach(glob('/fixture-support/*.schema.json') as $path){copy($path,$share.'/'.basename($path));chmod($share.'/'.basename($path),0644);}
}
$input=json_decode(file_get_contents('/fixtures/input.json'),true,32,JSON_THROW_ON_ERROR);
function tx(string $root,?string $crash=null):AsusImportTransaction{
    return new AsusImportTransaction(new AsusImportStore($root.'/journal',0),new AsusSmartDnsStore($root.'/dns',0),$root.'/resources',$root.'/resources/nfqws2.conf',0,
        ['checkpoint'=>static function($phase)use($crash){if($phase===$crash)exit(77);}]);
}
if($child){
    $root=$argv[3];$phase=$argv[4];$undo=str_starts_with($phase,'undo');$t=tx($root,$phase);
    if($undo)$t->undo(str_repeat('a',32));else $t->apply($t->prepare($input['docs'],$input['selection']),str_repeat('a',32));
    throw new RuntimeException('fixture_checkpoint_not_reached');
}
$assertions=0;$cases=0;
function check(bool $value,string $message):void{global $assertions;$assertions++;if(!$value)throw new RuntimeException($message);}
function fixture(string $name):string{
    global $input,$cases;$cases++;$root='/tmp/portable-assets/'.$name;mkdir($root.'/resources',0755,true);
    foreach(['lua','blobs','lists'] as $kind)mkdir($root.'/resources/'.$kind,0755);
    file_put_contents($root.'/resources/nfqws2.conf',$input['config']);chmod($root.'/resources/nfqws2.conf',0640);
    foreach(['lua/custom.lua','blobs/hello.bin'] as $name){file_put_contents($root.'/resources/'.$name,'ORIGINAL');chmod($root.'/resources/'.$name,0640);}
    return $root;
}
function originals(string $root):array{
    $rows=[];foreach(['lua/custom.lua','blobs/hello.bin'] as $name){$p=$root.'/resources/'.$name;clearstatcache(true,$p);$s=lstat($p);$rows[$name]=[file_get_contents($p),array_intersect_key($s,array_flip(['dev','ino','mode','uid','gid','mtime']))];}return $rows;
}
function target(string $root,string $kind):string{
    global $input;foreach(json_decode($input['docs'][1],true)['files'] as $file)if($file['kind']===$kind)return $root.'/resources/'.$kind.'/'.NfqwsResourcePaths::imported($kind,$file['sha256']);
    throw new RuntimeException('fixture_file_missing');
}
function crash(string $root,string $phase):void{
    global $platform;$pipes=[];$p=proc_open([PHP_BINARY,'-n','-d','register_argc_argv=1','-q','-f',__FILE__,'--','child',$platform,$root,$phase],[0=>['file','/dev/null','r'],1=>['pipe','w'],2=>['pipe','w']],$pipes);
    if(!is_resource($p))throw new RuntimeException('fixture_spawn');$out=stream_get_contents($pipes[1]);$err=stream_get_contents($pipes[2]);fclose($pipes[1]);fclose($pipes[2]);$exit=proc_close($p);
    check($exit===77&&$out===''&&$err==='','fixture_child_death_'.$phase.':'.$exit.':'.$out.':'.$err);
}
check(preg_match('/^Uid:\s+0\s+0\s+0\s+0$/m',file_get_contents('/proc/self/status'))===1,'actual_kernel_ROOT');
check(preg_match('/^Uid:\s+0\s+0\s+0\s+0$/m',file_get_contents('/proc/1/status'))===1,'owned_PID1_ROOT');
$root=fixture('commit');$before=originals($root);$t=tx($root);$p=$t->prepare($input['docs'],$input['selection']);
check($p['ready'],'actual_plan_ready');check($t->apply($p,str_repeat('a',32))['state']==='committed','actual_commit');
check($before===originals($root),'stock_exact_inode_metadata');
foreach(['lua','blobs'] as $kind){$path=target($root,$kind);$s=lstat($path);check($s['uid']===0&&($s['mode']&0777)===0644&&$s['nlink']===1,'actual_generated_owner_mode_'.$kind);}
check(str_contains(file_get_contents($root.'/resources/nfqws2.conf'),$platform==='openwrt'?'/etc/nfqws2/lua/imported/':'/opt/etc/nfqws2/lua/imported/'),'actual_platform_binding');
require '/fixtures/config.php';require $web.'/device-profiles-library.php';require $web.'/strategy-picker-core.php';
$library=new NfqwsDeviceProfilesLibrary($root.'/library',$root.'/snapshots',$root.'/resources',0,[]);
$saved=$library->capture('Portable custom assets');$entry=$library->entry($saved['id']);
check(isset($entry['files']['lua/'.NfqwsResourcePaths::imported('lua',hash_file('sha256',target($root,'lua')))]),'library_keeps_imported_identity');
$create=new ReflectionMethod($library,'create');$count=count($library->listing());
try{$create->invoke($library,'stale source',$p['config'],[],null,hash_file('sha256',$root.'/resources/nfqws2.conf'),['/opt/etc/nfqws2/blobs/hello.bin'=>str_repeat('0',64)]);throw new RuntimeException('fixture_expected_CAS');}
catch(RuntimeException $e){check($e->getMessage()==='source_changed','native_import_rechecks_resource_fingerprints');}
check(count($library->listing())===$count,'native_stale_import_creates_no_entry');
$retained=$root.'/retained';mkdir($retained,0755);foreach(['lua','blobs','lists'] as $kind)mkdir($retained.'/'.$kind,0755);
$config=NfqwsStrategyPickerResources::retain($entry,$root.'/snapshots/'.$saved['id'],$retained,0);
check(!str_contains(json_encode($config),'/snapshots/'),'native_retention_rebinds_all_paths');
foreach(['lua','blobs'] as $kind){$relative=$kind.'/'.NfqwsResourcePaths::imported($kind,hash_file('sha256',target($root,$kind)));check(is_file($retained.'/'.$relative),'retained_generated_namespace_'.$kind);check(str_contains(json_encode($config,JSON_UNESCAPED_SLASHES),$retained.'/'.$relative),'retained_generated_binding_'.$kind);}
check($before===originals($root),'native_capture_preserves_originals');
check($t->undo(str_repeat('a',32))['state']==='undone','actual_undo');check($before===originals($root),'undo_preserves_originals');
check(file_get_contents($root.'/resources/nfqws2.conf')===$input['config'],'config_exact_restore');
foreach(['directory_intent_blobs','directory_created_blobs','directory_blobs','directory_lua','stage_0','linked_0','file_0','file_1','draft','committing','config_stage','config','committed','undoing','undo_config','undo_file_0'] as $phase){
    $root=fixture('death-'.$phase);$before=originals($root);$t=tx($root);
    if(str_starts_with($phase,'undo'))$t->apply($t->prepare($input['docs'],$input['selection']),str_repeat('a',32));
    crash($root,$phase);
    if($phase==='directory_created_blobs'){
        try{$t->recover();throw new RuntimeException('fixture_expected_attention');}catch(RuntimeException $e){check($e->getMessage()==='restore_required','directory_gap_attention');}
        check($t->status()['state']==='restore_required','directory_gap_not_completed');continue;
    }
    $state=$t->recover()['state'];$after=in_array($phase,['config','committed'],true);
    check($state===($after?'committed':(str_starts_with($phase,'undo')?'undone':'rolled_back')),'correct_recovery_'.$phase);
    if($after)$t->undo(str_repeat('a',32));
    check(file_get_contents($root.'/resources/nfqws2.conf')===$input['config'],'restored_config_'.$phase);
    check($before===originals($root),'stock_unchanged_'.$phase);
    check(!file_exists(target($root,'lua'))&&!file_exists(target($root,'blobs')),'generated_files_restored_'.$phase);
}
$root=fixture('foreign');$t=tx($root);$t->apply($t->prepare($input['docs'],$input['selection']),str_repeat('a',32));$path=target($root,'blobs');$foreign=$path.'.foreign';copy($path,$foreign);rename($foreign,$path);$ino=lstat($path)['ino'];$config=file_get_contents($root.'/resources/nfqws2.conf');
try{$t->undo(str_repeat('a',32));throw new RuntimeException('fixture_expected_foreign_stop');}catch(RuntimeException $e){check($e->getMessage()==='source_changed','foreign_inode_refused');}
check(lstat($path)['ino']===$ino&&file_get_contents($root.'/resources/nfqws2.conf')===$config,'foreign_inode_and_config_preserved');
foreach(['symlink','hardlink','fifo'] as $kind){
    $root=fixture('unsafe-'.$kind);$path=target($root,'blobs');mkdir(dirname($path),0755);$outside=$root.'/outside.bin';file_put_contents($outside,'KEEP');
    if($kind==='symlink')symlink($outside,$path);elseif($kind==='hardlink')link($outside,$path);else check(NfqwsPlatform::run(['/bin/busybox','mkfifo',$path],2)['status']===0,'owned_fifo_created');
    $t=tx($root);$p=$t->prepare($input['docs'],$input['selection']);
    try{$t->apply($p,str_repeat('a',32));throw new RuntimeException('fixture_expected_unsafe_stop');}catch(RuntimeException $e){check($e->getMessage()==='source_changed','unsafe_target_refused_'.$kind);}
    check(!file_exists($root.'/journal/state.json')&&file_get_contents($outside)==='KEEP','unsafe_target_never_mutated_'.$kind);
}
$root=fixture('foreign-dir');$t=tx($root);$t->apply($t->prepare($input['docs'],$input['selection']),str_repeat('a',32));$dir=dirname(target($root,'blobs'));rename($dir,$dir.'-retained');mkdir($dir,0755);$config=file_get_contents($root.'/resources/nfqws2.conf');
try{$t->undo(str_repeat('a',32));throw new RuntimeException('fixture_expected_directory_stop');}catch(RuntimeException $e){check($e->getMessage()==='source_changed','foreign_directory_refused');}
check(file_get_contents($root.'/resources/nfqws2.conf')===$config,'foreign_directory_no_undo_effects');
// Substitutions happen after the earlier CAS/identity checks, under actual ROOT.
foreach(['stage_0','directory_blobs','file_1','config_stage'] as $phase){
    $root=fixture('late-'.$phase);$before=originals($root);
    $t=new AsusImportTransaction(new AsusImportStore($root.'/journal',0),new AsusSmartDnsStore($root.'/dns',0),$root.'/resources',$root.'/resources/nfqws2.conf',0,['checkpoint'=>function($p)use($root,$phase){
        if($p!==$phase)return;
        if($phase==='stage_0'){$path=glob($root.'/resources/blobs/imported/.import-*')[0];file_put_contents($root.'/foreign','FOREIGN');rename($root.'/foreign',$path);}
        elseif($phase==='directory_blobs'){$dir=$root.'/resources/blobs/imported';rename($dir,$dir.'-owned');mkdir($dir,0755);}
        else file_put_contents(target($root,'blobs'),'FOREIGN');
    }]);
    try{$t->apply($t->prepare($input['docs'],$input['selection']),str_repeat('a',32));throw new RuntimeException('fixture_expected_late_stop');}
    catch(RuntimeException $e){check(in_array($e->getMessage(),['source_changed','restore_required'],true),'late_substitution_refused_'.$phase);}
    check(file_get_contents($root.'/resources/nfqws2.conf')===$input['config'],'late_substitution_no_config_commit_'.$phase);
    check(originals($root)===$before,'late_substitution_stock_preserved_'.$phase);
}
$root=fixture('late-undo');$t=tx($root);$t->apply($t->prepare($input['docs'],$input['selection']),str_repeat('a',32));
$t=new AsusImportTransaction(new AsusImportStore($root.'/journal',0),new AsusSmartDnsStore($root.'/dns',0),$root.'/resources',$root.'/resources/nfqws2.conf',0,['checkpoint'=>function($p)use($root){
    if($p==='undo_config'){$path=target($root,'blobs');copy($path,$root.'/foreign');rename($root.'/foreign',$path);file_put_contents($root.'/foreign-inode',(string)lstat($path)['ino']);}
}]);
try{$t->undo(str_repeat('a',32));throw new RuntimeException('fixture_expected_late_undo_stop');}
catch(RuntimeException $e){check($e->getMessage()==='restore_required','late_foreign_undo_attention');}
check((string)lstat(target($root,'blobs'))['ino']===file_get_contents($root.'/foreign-inode'),'late_foreign_undo_inode_preserved');
echo json_encode(['passed'=>true,'assertions'=>$assertions,'platform'=>$platform,'kernel_uid'=>0,'cases'=>$cases,'scope'=>'offline owned ROOT storage and native library; no service/HTTP/router actions'],JSON_THROW_ON_ERROR);
