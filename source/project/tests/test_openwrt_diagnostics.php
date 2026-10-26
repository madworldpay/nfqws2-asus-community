<?php
require_once __DIR__.'/../webui/web/public/openwrt-dpi.php';
function check(bool $ok,string $label):void{if(!$ok)throw new RuntimeException($label);}
function denied(callable $f):void{try{$f();}catch(RuntimeException $e){return;}throw new RuntimeException('mismatched DPI installation accepted');}
$catalog=json_decode(file_get_contents(__DIR__.'/../openwrt/dpi-assets.json'),true);
foreach(['arm'=>'arm_cortex-a9','arm64'=>'aarch64_cortex-a53','mips'=>'mips_24kc','mipsel'=>'mipsel_24kc','x86_64'=>'x86_64']as $engine=>$arch){
 $record=['schema_version'=>1,'version'=>$catalog['version'],'arch'=>$arch,'engine'=>$engine,'artifact'=>$catalog['artifacts'][$engine]];
 check(NfqwsOpenWrtDpi::select($record,$arch,$engine)===$record['artifact'],'pinned native DPI selection');
 denied(fn()=>NfqwsOpenWrtDpi::select($record,'other_arch',$engine));
 denied(fn()=>NfqwsOpenWrtDpi::select($record,$arch,'other_engine'));
}
$record=['schema_version'=>1,'version'=>$catalog['version'],'arch'=>'mips64_octeonplus','engine'=>'mips64','artifact'=>null];
denied(fn()=>NfqwsOpenWrtDpi::select($record,'mips64_octeonplus','mips64'));
$elf=str_repeat("\0",64);$elf=substr_replace($elf,"\x7fELF\x01\x02\x01",0,7);$elf=substr_replace($elf,"\0\x08",18,2);
check(NfqwsOpenWrtDpi::matchesElf($elf,$catalog['artifacts']['mips']),'big-endian MIPS DPI header');
check(!NfqwsOpenWrtDpi::matchesElf($elf,$catalog['artifacts']['mipsel']),'opposite endianness rejected');
$elf[5]="\x01";$elf=substr_replace($elf,"\x28\0",18,2);
check(NfqwsOpenWrtDpi::matchesElf($elf,$catalog['artifacts']['arm']),'existing ARM little-endian header');
check(!NfqwsOpenWrtDpi::matchesElf('invalid',$catalog['artifacts']['arm']),'truncated header rejected');
echo "Native DPI artifact identity and endian boundaries passed\n";
