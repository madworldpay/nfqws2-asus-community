<?php
require_once __DIR__.'/../webui/web/public/openwrt-apk-trust.php';
function check(bool $ok,string $why):void{if(!$ok)throw new RuntimeException($why);}
$root=sys_get_temp_dir().'/nfqws-apk-keys-'.bin2hex(random_bytes(8));mkdir($root,0700);$mask=umask(0022);
foreach(['etc','lib']as $name)mkdir($root.'/'.$name,0755);
$own=file_get_contents(__DIR__.'/../updates/trusted-release-key.pem');
$other=openssl_pkey_get_details(openssl_pkey_new(['private_key_bits'=>2048,'private_key_type'=>OPENSSL_KEYTYPE_RSA]))['key'];
file_put_contents($root.'/etc/shared.pem',$other);file_put_contents($root.'/lib/shared.pem',$own);file_put_contents($root.'/lib/extra.pem',$own);file_put_contents($root.'/etc/README','not a key');
symlink($root.'/lib/extra.pem',$root.'/etc/linked.pem');
try{
 $result=NfqwsOpenWrtApkTrust::stage($root.'/merged',$own,[$root.'/etc',$root.'/lib'],getmyuid());
 check(file_get_contents($root.'/merged/shared.pem')===$other,'etc must shadow lib, as in native APK');
 check(file_get_contents($root.'/merged/extra.pem')===$own,'system/feed key lost');
 check(file_get_contents($root.'/merged/nfqws2-native-'.hash('sha256',$own).'.pem')===$own,'own release key missing');
 check(isset($result['files']['linked.pem']),'native trusted key links must be retained');
 check(file_get_contents($root.'/merged/linked.pem')===$own,'linked public key lost');
 check(count($result['files'])===4,'non-keys must not enter trusted keyring');
 foreach($result['files']as $name=>$sha){check(hash_file('sha256',$root.'/merged/'.$name)===$sha,'key fingerprint');check((fileperms($root.'/merged/'.$name)&0777)===0600,'private staged keyring permissions');}
 check((fileperms($root.'/merged')&0777)===0700,'private staged key directory');
 check(file_get_contents($root.'/etc/shared.pem')===$other&&file_get_contents($root.'/lib/shared.pem')===$own,'system keys changed');
 chmod($root.'/etc/shared.pem',0666);
 try{NfqwsOpenWrtApkTrust::stage($root.'/unsafe',$own,[$root.'/etc',$root.'/lib'],getmyuid());throw new LogicException('unsafe key accepted');}catch(RuntimeException $e){check($e->getMessage()==='invalid_state','unsafe key error');}
 check(!file_exists($root.'/unsafe'),'failed trust preflight created output');
 echo "Scoped APK trust retains system key precedence, adds our key and leaves global trust unchanged\n";
}finally{foreach(['etc','lib','merged','unsafe']as $dir)if(is_dir($root.'/'.$dir)){foreach(glob($root.'/'.$dir.'/*')as $p)unlink($p);rmdir($root.'/'.$dir);}rmdir($root);umask($mask);}
