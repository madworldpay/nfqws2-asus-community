<?php
$file=__DIR__.'/../webui/web/public/openwrt-smartdns-install.php';
if(!is_file($file))throw new RuntimeException('Native SmartDNS activation is missing');require_once $file;
function check(bool $ok,string $s):void{if(!$ok)throw new RuntimeException($s);}
function denied(callable $f):void{try{$f();}catch(RuntimeException $e){return;}throw new RuntimeException('Unsafe native SmartDNS accepted');}
$binary=str_repeat("\0",64);$binary=substr_replace($binary,"\x7fELF\x01\x02\x01",0,7);$binary=substr_replace($binary,"\0\x08",18,2);
$artifact=['source'=>'bundled-native','version'=>'1.2023.43','version_output'=>'smartdns 1.2023.43','sha256'=>hash('sha256',$binary),
 'elf_class'=>1,'elf_data'=>2,'elf_machine'=>8,'files'=>['smartdns'=>['size'=>64,'sha256'=>hash('sha256',$binary)]],'links'=>[]];
$record=['schema_version'=>1,'series'=>'24.10','arch'=>'mips_24kc','artifact'=>$artifact];
check(NfqwsOpenWrtSmartDnsInstall::select($record,'24.10','mips_24kc')===$artifact,'Exact native artifact selection');
denied(fn()=>NfqwsOpenWrtSmartDnsInstall::select($record,'25.12','mips_24kc'));
denied(fn()=>NfqwsOpenWrtSmartDnsInstall::select($record,'24.10','mipsel_24kc'));
$root=sys_get_temp_dir().'/nfqws-native-dns-install-'.bin2hex(random_bytes(6));mkdir($root,0700);mkdir($root.'/stage',0700);file_put_contents($root.'/source',$binary);chmod($root.'/source',0600);
try{
 NfqwsOpenWrtSmartDnsInstall::stage($artifact,$root.'/source',$root.'/stage',getmyuid());
 check(file_get_contents($root.'/stage/smartdns')===$binary,'Native engine bytes');check((fileperms($root.'/stage/smartdns')&0777)===0700,'Executable kept private');
 unlink($root.'/stage/smartdns');file_put_contents($root.'/source',$binary.'tamper');
 denied(fn()=>NfqwsOpenWrtSmartDnsInstall::stage($artifact,$root.'/source',$root.'/stage',getmyuid()));check(!file_exists($root.'/stage/smartdns'),'Tampered engine not staged');
 unlink($root.'/source');symlink('/etc/passwd',$root.'/source');denied(fn()=>NfqwsOpenWrtSmartDnsInstall::stage($artifact,$root.'/source',$root.'/stage',getmyuid()));
 echo "Native SmartDNS exact identity, endian and activation verification passed\n";
}finally{foreach(glob($root.'/stage/*')as $f)unlink($f);rmdir($root.'/stage');unlink($root.'/source');rmdir($root);}
