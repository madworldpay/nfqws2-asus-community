<?php
require_once __DIR__.'/update-lifecycle.php';
/** Reconstruct a known APK mutation as a non-overridable, read-only simulation. */
final class NfqwsOpenWrtApkCommand
{
    private const VALUES=['keys-dir','repositories-file','repository','repository-config','cache-dir','timeout','wait','arch','root','virtual','cache-max-age'];
    private const BOOLS=['network','cache','cache-packages','cache-predownload','check-certificate','commit-hooks','scripts','simulate','progress','pretty-print','interactive','purge','clean-protected','sync','root-tmpfs','preserve-env','logfile','legacy-info'];
    private const FLAGS=['quiet','verbose','upgrade','latest','force-reinstall','force','force-broken-world','force-missing-repositories','force-no-chroot','force-non-repository','force-old-apk','force-overwrite','force-refresh','no-chown','usermode','initdb','initramfs-diskless-boot','rdepends','recursive'];
    private static function fail():never{throw new RuntimeException('unsupported_manager_command');}
    /** Called only from the fixed root CLI adapter, inside the real APK hook. */
    public static function manager():array
    {
        $exe=realpath('/usr/bin/apk');if($exe===false)throw new RuntimeException('invalid_state');$pid=getmypid();$seen=[];
        for($n=0;$n<32&&$pid>1;$n++){
            if(isset($seen[$pid]))break;$seen[$pid]=true;$identity=AsusUpdateLifecycle::identity($pid);
            if(is_array($identity)&&$identity['exe']===$exe&&$identity['uid']===0){
                $raw=@file_get_contents('/proc/'.$pid.'/cmdline',false,null,0,65537);
                if(!is_string($raw)||strlen($raw)>65536||!str_ends_with($raw,"\0")||AsusUpdateLifecycle::identity($pid)!==$identity)throw new RuntimeException('invalid_state');
                return ['identity'=>$identity,'argv'=>explode("\0",substr($raw,0,-1))];
            }
            $raw=@file_get_contents('/proc/'.$pid.'/status');if(!is_string($raw)||!preg_match('/^PPid:\s+([0-9]+)/m',$raw,$m))break;$pid=(int)$m[1];
        }
        throw new RuntimeException('invalid_state');
    }
    public static function simulation(array $argv):array
    {
        if(!array_is_list($argv)||count($argv)<2||count($argv)>512)self::fail();$bytes=0;
        foreach($argv as $value){if(!is_string($value)||strpbrk($value,"\0\r\n")!==false||strlen($value)>8192)self::fail();$bytes+=strlen($value);}
        if($bytes>65536||!in_array($argv[0],array_filter(['apk','/usr/bin/apk',realpath('/usr/bin/apk')]),true))self::fail();
        $options=[];$operands=[];$command=null;$literal=false;
        $option=function(string $key,?string $value=null)use(&$options){
            if(in_array($key,self::VALUES,true)){
                if($value===null||$value===''||($key==='root'&&$value!=='/'))self::fail();$options[]='--'.$key;$options[]=$value;return;
            }
            if(in_array($key,self::BOOLS,true)){
                if($value!==null&&!in_array(strtolower($value),['yes','no','true','false','1','0','auto'],true))self::fail();
                if(in_array($key,['simulate','pretty-print','progress'],true))return;$options[]='--'.$key.($value===null?'':'='.$value);return;
            }
            if(!in_array($key,self::FLAGS,true)||$value!==null)self::fail();$options[]='--'.$key;
        };
        for($i=1;$i<count($argv);$i++){
            $arg=$argv[$i];if(!$literal&&$arg==='--'){$literal=true;continue;}
            if(!$literal&&str_starts_with($arg,'--')){
                $pair=explode('=',substr($arg,2),2);$key=$pair[0];$value=$pair[1]??null;
                if(in_array($key,self::VALUES,true)&&$value===null){if(!isset($argv[++$i]))self::fail();$value=$argv[$i];}
                $option($key,$value);continue;
            }
            if(!$literal&&str_starts_with($arg,'-')&&$arg!=='-'){
                $map=['q'=>'quiet','v'=>'verbose','u'=>'upgrade','l'=>'latest','f'=>'force','s'=>'simulate','U'=>'cache-max-age','X'=>'repository','p'=>'root','t'=>'virtual','r'=>'rdepends'];
                for($n=1;$n<strlen($arg);$n++){
                    $key=$map[$arg[$n]]??null;if($key===null)self::fail();
                    if($arg[$n]==='U'){$option('cache-max-age','0');continue;}
                    if(in_array($key,self::VALUES,true)){$value=substr($arg,$n+1);if($value===''){if(!isset($argv[++$i]))self::fail();$value=$argv[$i];}$option($key,$value);break;}
                    $option($key);
                }continue;
            }
            if($command===null){if($literal||!in_array($arg,['add','del','upgrade','fix'],true))self::fail();$command=$arg;}else $operands[]=$arg;
        }
        if($command===null||in_array($command,['add','del'],true)&&$operands===[])self::fail();
        return array_merge(['/usr/bin/apk'],$options,[$command,'--simulate=yes','--pretty-print=no','--progress=no','--'],$operands);
    }
    public static function affects(string $output):?string
    {
        if(strlen($output)>65536||str_contains($output,"\0"))self::fail();$mode=null;
        foreach(explode("\n",$output)as $line){
            if(!preg_match('/^\([ \t]*[0-9]+\/[ \t]*[0-9]+\)/',$line))continue;
            if(!preg_match('/^\([ \t]*[0-9]+\/[ \t]*[0-9]+\) (Installing|Upgrading|Downgrading|Reinstalling|Purging|Removing|Replacing) ([a-z0-9][a-z0-9+._-]{0,127}) \([^\r\n]*\)$/D',$line,$m))self::fail();
            if($m[2]!=='nfqws2-native')continue;
            if(in_array($m[1],['Purging','Removing'],true))$mode='remove';elseif($mode!=='remove')$mode='upgrade';
        }
        return $mode;
    }
}
