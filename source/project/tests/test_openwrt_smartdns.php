<?php
require_once __DIR__.'/../webui/web/public/smartdns-install.php';
require_once __DIR__.'/../webui/web/public/openwrt-smartdns-resolver.php';
function check(bool $ok,string $why):void{if(!$ok)throw new RuntimeException($why);}
function rejects(callable $fn,string $why):void{try{$fn();}catch(RuntimeException $e){return;}throw new RuntimeException($why);}
check(class_exists('NfqwsOpenWrtDnsmasqOverlay'),'Native transactional resolver overlay is missing');
$frame=['name'=>'dnsmasq','instances'=>['main'=>['command'=>['/usr/sbin/dnsmasq','-C','/var/etc/dnsmasq.conf.main','-k'],
 'env'=>['KEEP_OPERATOR_VALUE'=>'keep'],'file'=>['/etc/config/dhcp'],'jail'=>['name'=>'dnsmasq','requirejail'=>true],'opaque_future_policy'=>['required'=>true]]]];
$before=$frame;
NfqwsOpenWrtDnsmasqResolver::validateCommit($frame,'main','/var/etc/dnsmasq.conf.main');
check($frame===$before,'native procd metadata must pass unchanged, including hidden/future policy');
$generation=str_repeat('a',32).':restore:'.str_repeat('b',16);
$owned=$frame;$owned['instances']['main']['env']['NFQWS2_DNS_GENERATION']=$generation;
NfqwsOpenWrtDnsmasqResolver::validateCommit($owned,'main','/var/etc/dnsmasq.conf.main',$generation);
rejects(fn()=>NfqwsOpenWrtDnsmasqResolver::validateCommit($frame,'main','/var/etc/dnsmasq.conf.main',$generation),'generation must reach native transport');
rejects(fn()=>NfqwsOpenWrtDnsmasqResolver::validateCommit($owned,'main','/var/etc/dnsmasq.conf.main',str_repeat('c',32).':forward:'.str_repeat('d',16)),'wrong generation must not cross the commit boundary');
$both=$frame;$both['instances']['guest']=$frame['instances']['main'];rejects(fn()=>NfqwsOpenWrtDnsmasqResolver::validateCommit($both,'main','/var/etc/dnsmasq.conf.main'),'must not commit another instance');
$foreign=$frame;$foreign['instances']['main']['command'][0]='/bin/sh';rejects(fn()=>NfqwsOpenWrtDnsmasqResolver::validateCommit($foreign,'main','/var/etc/dnsmasq.conf.main'),'must not replace another command');
rejects(fn()=>NfqwsOpenWrtDnsmasqResolver::validateCommit($frame,'main','/var/etc/dnsmasq.conf.guest'),'must not adopt another config');
$root=sys_get_temp_dir().'/nfqws-dns-overlay-'.bin2hex(random_bytes(8));mkdir($root,0700);
$original="server=8.8.8.8\nconf-file=$root/vpn.conf\nresolv-file=$root/resolv.conf\n";
$vpn="server=/corp.example/10.7.0.1\nipset=/video.example/vpn_dst\nnftset=/video.example/4#inet#fw4#vpn_dst\n";
file_put_contents($root.'/generated.conf',$original);chmod($root.'/generated.conf',0644);file_put_contents($root.'/vpn.conf',$vpn);file_put_contents($root.'/guest.conf',"server=192.0.2.3\n");
$snapshot=['config'=>$root.'/generated.conf','original'=>$original,'mode'=>0644,'text'=>"server=8.8.8.8\n".$vpn];
try{
 $overlay=new NfqwsOpenWrtDnsmasqOverlay(getmyuid());check($overlay->routing($snapshot)==='external','initial ordinary DNS');$overlay->apply($snapshot);
 $effective=file_get_contents($root.'/generated.conf');check(str_contains($effective,'server=127.0.0.1#6054'),'exclusive managed default');check(!str_contains($effective,'server=8.8.8.8'),'old default must not race managed DNS');check(str_contains($effective,$vpn),'conditional server/ipset/nftset must survive');
 check(file_get_contents($root.'/vpn.conf')===$vpn,'persistent VPN file changed');check(file_get_contents($root.'/guest.conf')==="server=192.0.2.3\n",'guest changed');check($overlay->routing($snapshot)==='managed','effective DNS identity');
 rejects(fn()=>$overlay->apply($snapshot),'must not adopt or replay a managed config');
 file_put_contents($root.'/generated.conf',$effective."# operator edit\n");check($overlay->routing($snapshot)==='unknown','operator edit must be a conflict');rejects(fn()=>$overlay->apply($snapshot),'operator edit must survive a repeated apply');check(str_ends_with(file_get_contents($root.'/generated.conf'),"# operator edit\n"),'operator edit overwritten');
 unlink($root.'/generated.conf');symlink($root.'/guest.conf',$root.'/generated.conf');rejects(fn()=>$overlay->apply($snapshot),'alias must not be overwritten');check($overlay->routing($snapshot)==='unknown','foreign link must not be adopted');
 $instances=['main'=>['running'=>true,'pid'=>121,'command'=>['/usr/sbin/dnsmasq','-C','/var/etc/dnsmasq.conf.main','-k']],'guest'=>['running'=>true,'pid'=>122,'command'=>['/usr/sbin/dnsmasq','-C','/var/etc/dnsmasq.conf.guest','-k']]];
 check(NfqwsOpenWrtDnsmasqResolver::select($instances,[121])['instance']==='main','selected wrong DNS instance');
 $jailed=$instances;$jailed['main']['pid']=120;
 check(NfqwsOpenWrtDnsmasqResolver::select($jailed,[121],[121=>120])['instance']==='main','native ujail child must match its supervised instance');
 rejects(fn()=>NfqwsOpenWrtDnsmasqResolver::select($jailed,[121],[121=>119]),'unrelated child must not match supervisor');
 rejects(fn()=>NfqwsOpenWrtDnsmasqResolver::select($jailed,[121],[121=>121]),'cyclic ancestry must be rejected');
 foreach([[121,122],[999],[]]as $owners)rejects(fn()=>NfqwsOpenWrtDnsmasqResolver::select($instances,$owners),'ambiguous or foreign DNS owner must be rejected');
 echo "Native DNS CAS overlay, persistent VPN preservation and instance isolation passed\n";
}finally{foreach(glob($root.'/*')as $p)unlink($p);rmdir($root);}
