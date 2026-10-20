<?php
require __DIR__.'/support_report_fixture.php';
require __DIR__.'/../webui/web/public/support-report.php';
class RelayReportFixtureIO extends ReportFixtureIO {
    public ?AsusReportIO $headers = null;
    public function engine(): array { return $this->headers ? $this->headers->engine() : parent::engine(); }
    public function runtimeComponents(?string $abi): array { return $this->headers ? $this->headers->runtimeComponents($abi) : parent::runtimeComponents($abi); }
}
$io = new RelayReportFixtureIO();
if(($argv[1]??'')==='corrupt-elf') $io->headers=new AsusReportIO(['opt'=>$argv[2]]);
$io->files['config'] = "NFQUEUE_NUM=300\nASUS_CLIENT_MODE=include\nASUS_CLIENTS4=192.0.2.4\nASUS_CLIENTS6=\nTCP_PORTS=80,443\nUDP_PORTS=443\nIPV6_ENABLED=0\nISP_INTERFACE=\n";
if(in_array($argv[1]??'', ['clients65','clients128'],true)) {
    $v4=implode(' ',array_map(fn($n)=>'192.0.2.'.$n,range(1,64)));
    $v6=implode(' ',array_map(fn($n)=>'2001:db8::'.dechex($n),range(1,$argv[1]==='clients65'?1:64)));
    $io->files['config']=str_replace(['ASUS_CLIENTS4=192.0.2.4','ASUS_CLIENTS6='],["ASUS_CLIENTS4='".$v4."'","ASUS_CLIENTS6='".$v6."'"],$io->files['config']);
}
$io->files['runtime'] = $io->files['config'];
$io->files['queue'] = "300 345 0 2 65535 0 0 4294967295 1\n";
$io->files['kernel']='4.19.294';
$io->files['opkg']="arch all 100\narch aarch64-3.10 160";
$io->commands['nvram']="productid=GT-BE19000AI\nfirmver=3006\nbuildno=102\nextendno=9_0\nsw_mode=1\n";
$io->commands['machine']='aarch64';
$io->commands['links']='2: eth0: <UP> mtu 1500';
$io->commands['addr4']='2: eth0    inet 192.0.2.1/24';
$io->commands['route4']='default via 192.0.2.254 dev eth0';
foreach(['addr6','route6'] as $k)$io->commands[$k]='';
$io->files['tables4']="mangle\nnat\n";
$io->files['tables6']='';
$io->commands['rules4-nat']='[0:0] -A nfqa_nat -j MASQUERADE';
$io->commands['rules4-mangle']="[1:74] -A PREROUTING -j nfqa_pre\n[4294967295:18446744073709551615] -A nfqa_pre -i eth0 -s 192.0.2.4 -p tcp -m conntrack --ctorigsrc 192.0.2.4 --ctdir ORIGINAL --dport 443 -j NFQUEUE --queue-num 300 --queue-bypass";
$io->inventory['list']['custom.txt']="example.invalid\n";
$io->inventory['lua']['custom.lua']='-- placeholder';
$io->inventory['blob']['custom.bin']='sample';
$r=(new AsusSupportReport($io,new AsusReportValues()))->collect();
$r['captured_at']='2026-10-15T12:30:45Z';
if(($argv[1]??'')==='truncated')foreach($r['sections'] as $k=>$_)$r['sections'][$k]=['state'=>'unavailable','data'=>[],'reason'=>'truncated'];
echo AsusSupportReport::encode($r);
