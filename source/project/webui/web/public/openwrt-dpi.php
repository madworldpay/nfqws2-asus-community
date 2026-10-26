<?php
require_once __DIR__.'/platform.php';
/** Native DPI identity is packaged for the exact firmware architecture. */
final class NfqwsOpenWrtDpi
{
    private const ELF=['arm'=>[1,1,40],'arm64'=>[2,1,183],'mips'=>[1,2,8],'mipsel'=>[1,1,8],'x86_64'=>[2,1,62]];
    private static function read(string $name):array
    {
        $path=NfqwsPlatform::sharedFile($name,__DIR__.'/missing-native-dpi.json');
        $raw=@file_get_contents($path,false,null,0,16385);
        if(!is_string($raw)||strlen($raw)>16384)throw new RuntimeException('unsupported_abi');
        $v=json_decode($raw,true);if(!is_array($v))throw new RuntimeException('unsupported_abi');return $v;
    }
    public static function artifact():array
    {
        preg_match("/^DISTRIB_ARCH='([A-Za-z0-9_.-]{1,64})'$/m",(string)@file_get_contents('/etc/openwrt_release',false,null,0,4096),$m);
        $installed=self::read('platform.json');
        if(($installed['platform']??null)!=='openwrt'||($installed['arch']??null)!==($m[1]??null))throw new RuntimeException('unsupported_abi');
        return self::select(self::read('dpi-native-artifact.json'),$m[1],$installed['engine']??'');
    }
    public static function select(array $record,string $arch,string $engine):array
    {
        if(($record['schema_version']??null)!==1||($record['arch']??null)!==$arch||($record['engine']??null)!==$engine||
            !isset(self::ELF[$engine])||!is_array($record['artifact']??null))throw new RuntimeException('unsupported_abi');
        $v=$record['artifact'];$version=$record['version']??'';
        if(!is_string($version)||!preg_match('/^v[A-Za-z0-9.-]{1,63}$/D',$version)||
            !is_int($v['size']??null)||$v['size']<20||$v['size']>8388608||
            !is_string($v['sha256']??null)||!preg_match('/^[a-f0-9]{64}$/D',$v['sha256'])||
            [$v['elf_class']??null,$v['elf_data']??null,$v['elf_machine']??null]!==self::ELF[$engine])throw new RuntimeException('unsupported_abi');
        if(($v['source']??null)==='bundled-legacy'){
            if($engine!=='arm'||($v['name']??null)!=='dpi-detector-armv5te'||
                ($v['source_commit']??null)!=='a09d03b58d452c71bd63a9b3d410713dd22049f6'||
                ($v['build_target']??null)!=='armv5te-unknown-linux-musleabi'||
                $v['sha256']!=='c0e0045bab2ae654a9f0fef125602fc042b6f54705afdfa0d6bfc10557e74863'||$v['size']!==3778448)throw new RuntimeException('unsupported_abi');
        }elseif(!is_string($v['name']??null)||!preg_match('/^dpi-detector-linux-(?:armv7|arm64|mips|mipsel|x86_64)$/D',$v['name'])||
            ($v['url']??null)!=='https://github.com/Runnin4ik/dpi-detector/releases/download/'.$version.'/'.$v['name'])throw new RuntimeException('unsupported_abi');
        return $v;
    }
    /** Preserve the existing little-endian contract and support pinned MIPS BE. */
    public static function matchesElf(string $elf,array $artifact):bool
    {
        $data=$artifact['elf_data']??1;
        return strlen($elf)>=20&&substr($elf,0,4)==="\x7fELF"&&in_array($data,[1,2],true)&&
            ord($elf[4])===($artifact['elf_class']??null)&&ord($elf[5])===$data&&
            unpack($data===1?'v':'n',substr($elf,18,2))[1]===($artifact['elf_machine']??null);
    }
}
