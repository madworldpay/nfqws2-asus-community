<?php
require __DIR__.'/support_report_fixture.php';
require __DIR__.'/../webui/web/public/support-report.php';
$cases=[];
$cases['process scheduling is not a restart']=function(){
 $io=new ReportFixtureIO();$r=new AsusSupportReport($io,new AsusReportValues());
 $id=['boot'=>'boot','pid'=>345,'start_ticks'=>'999','exe'=>'/opt/usr/bin/nfqws2','running'=>true,'uid'=>65534,'process_state'=>'S'];
 $io->files['queue']="300 345 0 2 65535 0 0 10 1\n";$a=$r->queueSample(300,$id);
 $id['process_state']='R';$io->files['queue']="300 345 0 2 65535 0 0 15 1\n";$b=$r->queueSample(300,$id);
 reportCheck($r->compareQueue($a,$b)['result']==='increased','S to R keeps stable identity');
};
$cases['opkg quoted-token regressions']=function(){
 foreach([
  ['arch armv7-2.6 "160"junk', 'armv7-3.2'],
  ['"arch""armv7-2.6""160"', 'armv7-2.6'],
  ['arch armv7-2.6 "160 spaces"', 'armv7-2.6'],
  ['arch armv7-2.6 160 # comment', 'armv7-3.2'],
  ['arch armv7-2.6 160 extra', 'armv7-2.6'],
  ['arch armv7-2.6 160 "one word"', 'armv7-3.2'],
 ] as [$text,$expected])reportCheck(AsusReportPlatform::abi($text."\narch armv7-3.2 1\n")===$expected,'ABI '.$text);
};
$cases['actual conntrack client selector and NAT target']=function(){
 $io=new ReportFixtureIO();$v=new AsusReportValues();
 $io->files['tables4']="mangle\nnat\n";$io->files['tables6']='';
 $io->commands['rules4-mangle']="[2:160] -A nfqa_post -o wan0 -m conntrack --ctdir ORIGINAL --ctorigsrc 192.168.50.1/32 -j nfqa_out\n";
 $io->commands['rules4-nat']="[1:40] -A nfqa_nat -p tcp -m mark --mark 0x40000000/0x40000000 -j MASQUERADE\n";
 $settings=['ASUS_CLIENTS4'=>'192.168.50.1','ASUS_CLIENT_MODE'=>'include','ISP_INTERFACE'=>'wan0'];
 $s=(new AsusReportNetwork($io,$v))->collect($settings,$settings);$rules=$s['rules']['data']['items'];
 reportCheck(($rules[0]['selectors']['original_source']['id']??null)===$s['settings']['data']['saved']['clients4']['ids'][0],'same client ID');
 reportCheck(($rules[0]['selectors']['ctdir']??null)==='ORIGINAL'&&!$rules[0]['incomplete'],'actual client direction selector');
 reportCheck($rules[1]['target']==='MASQUERADE'&&!$rules[1]['incomplete'],'own NAT target');
};
$cases['startup prerequisites distinguish missing runtime']=function(){
 $io=new ReportFixtureIO();$s=(new AsusReportPlatform($io,new AsusReportValues()))->collect();
 reportCheck(isset($s['package']['data']['runtime_components']),'fixed runtime availability');
 reportCheck(in_array('configuration_missing',$s['errors']['data']['observed_prerequisite_failures']??[],true),'configuration failure code');
 reportCheck(in_array('runtime_unavailable',$s['errors']['data']['observed_prerequisite_failures']??[],true),'runtime failure code');
};
$cases['sample gap excludes preparation time']=function(){
 $io=new class extends ReportFixtureIO {
  private bool $firstRead=true;
  public function read(string $id,int $limit=262144):array {
   if($this->firstRead){$this->firstRead=false;$this->time+=1;}
   return parent::read($id,$limit);
  }
 };
 $report=(new AsusSupportReport($io,new AsusReportValues()))->collect();
 reportCheck($report['sections']['nfqueue']['data']['comparison']['interval_ms']>=10000,'ten seconds between samples');
};
$cases['ABI is unknown after unreadable dropin']=function(){
 $io=new class extends ReportFixtureIO {
  public function readResource(string $kind,string $name,int $limit=262144):array{return ['state'=>'denied','value'=>''];}
 };
 $io->files['opkg']="arch armv7-3.2 1\n";$io->inventory['opkg']=['priority.conf'=>''];
 $s=(new AsusReportPlatform($io,new AsusReportValues()))->collect();
 reportCheck($s['package']['data']['entware_abi']===null,'do not infer primary ABI from incomplete inputs');
};
$cases['JSON size includes final newline']=function(){
 $r=['complete'=>true,'sections'=>['platform'=>['state'=>'available','data'=>['value'=>'']]],'failures'=>[]];
 $size=strlen(json_encode($r,JSON_PRETTY_PRINT|JSON_UNESCAPED_SLASHES));
 $r['sections']['platform']['data']['value']=str_repeat('a',1048576-$size);
 reportCheck(strlen(AsusSupportReport::encode($r))<=1048576,'newline within one MiB');
};
$failed=0;foreach($cases as $name=>$case)try{$case();echo "PASS $name\n";}catch(Throwable $e){++$failed;echo "FAIL $name: ".$e->getMessage()."\n";}
exit($failed?1:0);
