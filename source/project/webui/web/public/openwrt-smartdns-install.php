<?php
require_once __DIR__.'/platform.php';
require_once __DIR__.'/openwrt-dpi.php';
/** Engine-only native payload; never install stock resolver service/config files. */
final class NfqwsOpenWrtSmartDnsInstall
{
    public static function select(array $record,string $series,string $arch):array
    {
        $a=$record['artifact']??null;
        if(($record['schema_version']??null)!==1||($record['series']??null)!==$series||($record['arch']??null)!==$arch||!is_array($a)||
            ($a['source']??null)!=='bundled-native'||!is_string($a['version']??null)||!preg_match('/^[0-9][a-zA-Z0-9.+-]{0,63}$/D',$a['version'])||
            ($a['version_output']??null)!=='smartdns '.$a['version']||!is_string($a['sha256']??null)||!preg_match('/^[a-f0-9]{64}$/D',$a['sha256'])||
            !in_array($a['elf_class']??null,[1,2],true)||!in_array($a['elf_data']??null,[1,2],true)||!in_array($a['elf_machine']??null,[3,8,40,62,183],true)||
            ($a['links']??null)!==[]||array_keys($a['files']??[])!==['smartdns'])throw new RuntimeException('unsupported_abi');
        $f=$a['files']['smartdns'];if(!is_int($f['size']??null)||$f['size']<20||$f['size']>8388608||($f['sha256']??null)!==$a['sha256'])throw new RuntimeException('unsupported_abi');
        return $a;
    }
    public static function artifact():array
    {
        $file=NfqwsPlatform::sharedFile('smartdns-native-artifact.json',__DIR__.'/missing-native-smartdns.json');
        $raw=@file_get_contents($file,false,null,0,8193);$record=is_string($raw)&&strlen($raw)<=8192?json_decode($raw,true):null;
        $release=(string)@file_get_contents('/etc/openwrt_release',false,null,0,4096);
        preg_match("/^DISTRIB_ARCH='([A-Za-z0-9_.-]{1,64})'$/m",$release,$arch);preg_match("/^DISTRIB_RELEASE='([0-9]{2}\\.[0-9]{2})\\.[0-9]+'$/m",$release,$series);
        if(!is_array($record)||!isset($arch[1],$series[1]))throw new RuntimeException('unsupported_abi');return self::select($record,$series[1],$arch[1]);
    }
    public static function stage(array $artifact,string $source,string $stage,int $owner=0):void
    {
        $file=NfqwsPlatform::guardFile(dirname($source),basename($source),$owner);$s=@lstat($file);$want=$artifact['files']['smartdns'];
        if(!$s||$s['uid']!==$owner||($s['mode']&0022)!==0||$s['size']!==$want['size']||!hash_equals($want['sha256'],hash_file('sha256',$file)))throw new RuntimeException('download_hash');
        $elf=file_get_contents($file,false,null,0,64);if(!NfqwsOpenWrtDpi::matchesElf($elf,$artifact))throw new RuntimeException('unsupported_binary');
        $target=NfqwsPlatform::guardFile($stage,'smartdns',$owner);if(file_exists($target)||is_link($target))throw new RuntimeException('invalid_state');
        $mask=umask(0077);try{$f=@fopen($target,'xb');}finally{umask($mask);}if(!$f)throw new RuntimeException('invalid_state');
        try{$in=fopen($file,'rb');try{if(stream_copy_to_stream($in,$f)!==$want['size']||!fflush($f)||!chmod($target,0700))throw new RuntimeException('insufficient_space');}finally{fclose($in);}}
        finally{fclose($f);}
        if(!hash_equals($want['sha256'],hash_file('sha256',$target)))throw new RuntimeException('download_hash');
    }
}
