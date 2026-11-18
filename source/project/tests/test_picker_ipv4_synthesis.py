"""Destination scope survives assembly without turning IPs into hostlists."""
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import unittest
from test_dpi_normalize import PHP, PUBLIC


SETUP=r'''
require $argv[1].'/strategy-synthesis.php';require $argv[1].'/strategy-picker-custom-score.php';
$hosts=['8.8.8.8','1.1.1.1','example.com'];$nativeHosts=['example.com','child.example.com','grand.child.example.com','other.net'];
$manifest=NfqwsStrategyPickerCustomWorker::prepareDocument($hosts,str_repeat('d',64));
$manifest+=['pins'=>array_map(static fn($h)=>['host'=>$h,'answer'=>[$h==='example.com'?'8.8.8.8':$h],'address'=>$h==='example.com'?'8.8.8.8':$h],$hosts),
 'policy'=>NfqwsIdna::POLICY,'fingerprint'=>AsusDpiSiteCheckProbe::MIXED_PINNED_FINGERPRINT];
$sha=hash('sha256',json_encode($manifest,JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR));$id=0;
$make=static function($recipe,$nativeGood,$customGood)use($hosts,$nativeHosts,$manifest,$sha,&$id){
 $recipe=NfqwsStrategySynthesis::forTargets($recipe,$manifest,$nativeHosts);
 $native=['targets'=>'native-same','context_sha256'=>str_repeat('c',64),
  'metrics'=>array_fill_keys(['tcp','http','tls12','tls13','quic'],['ok'=>count($nativeGood),'total'=>4]),'domains'=>[]];
 foreach($nativeHosts as $h)$native['domains'][$h]=array_fill_keys(['http','tls12','tls13','quic'],in_array($h,$nativeGood,true));
 $e=['schema_version'=>2,'hosts'=>$hosts,'dns_context'=>$manifest['dns_context'],'fingerprint'=>$manifest['fingerprint'],
  'target_policy_version'=>$manifest['target_policy_version'],'targets'=>$manifest['targets'],'observations'=>[],'manifest_sha256'=>$sha];
 foreach($hosts as $h)foreach(['tls12','tls13']as $tls){$r=AsusDpiSiteCheck::response('response');$r['http_status']=in_array($h,$customGood,true)?200:403;
  $e['observations'][]=['host'=>$h,'tls'=>$tls,'response'=>$r];}
 $scores=[];for($i=0;$i<2;$i++)$scores[]=NfqwsStrategyPickerCustomScore::measure($e,str_repeat('c',64),str_pad(dechex(++$id),32,'0',STR_PAD_LEFT));
 return ['recipe'=>$recipe,'runs'=>[$native,$native],'custom_runs'=>$scores,'custom_manifest'=>$manifest];
};
$matrix=NfqwsStrategySynthesis::matrix(['max_repeats'=>4]);$a=$matrix['initial'][0];$b=$matrix['initial'][1];
$observations=[$make(NfqwsStrategySynthesis::blank(),[],[]),$make($a,$nativeHosts,['example.com']),$make($b,[],['8.8.8.8','1.1.1.1'])];
$base=['NFQWS_EXTRA_ARGS'=>'--hostlist=/tmp/user.list --hostlist-auto=/tmp/auto.list --hostlist-exclude=/tmp/exclude.list'];
'''


class Ipv4SynthesisTests(unittest.TestCase):
    def php(self,body):
        r=subprocess.run([PHP,'-n','-r',SETUP+"try{"+body+"}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}",str(PUBLIC)],
            capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'')
        return json.loads(r.stdout)

    def test_scope_materializes_literal_even_when_component_equals_global_or_pass(self):
        out=self.php("$out=[];foreach([$a,NfqwsStrategySynthesis::blank()]as $r){$s=NfqwsStrategySynthesis::forTargets($r,$manifest,$nativeHosts);$out[]=['recipe'=>$s,'config'=>NfqwsStrategySynthesis::bind($s,$base)];}echo json_encode($out);")
        self.assertIsInstance(out,list,out)
        for row in out:
            self.assertEqual(row['recipe']['custom_scope']['manifest_sha256'],self.manifest_sha(row['recipe']['custom_scope']['manifest']))
            ips=[o for o in row['recipe']['overrides']if 'addresses'in o]
            self.assertEqual(ips,[dict(protocol='tls',addresses=['8.8.8.8','1.1.1.1'],component=row['recipe']['tls'])])
            self.assertNotIn('--hostlist-domains=8.8.8.8',row['config']['NFQWS_ARGS_CUSTOM'])
            self.assertIn('--ipset-ip=8.8.8.8,1.1.1.1',row['config']['NFQWS_ARGS_CUSTOM'])

    @staticmethod
    def manifest_sha(value):
        import hashlib
        return hashlib.sha256(json.dumps(value,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

    def test_assembly_selects_ip_from_own_tls_evidence_and_keeps_domain_cdn_scope_separate(self):
        out=self.php("$r=NfqwsStrategySynthesis::assemble($observations);echo json_encode(['recipe'=>$r,'config'=>NfqwsStrategySynthesis::bind($r,$base),'ip_component'=>$b['tls'],'domain_component'=>$a['tls']]);")
        self.assertNotIn('error',out);recipe=out['recipe']
        self.assertEqual(recipe['tls'],out['domain_component'])
        ips=[o for o in recipe['overrides']if 'addresses'in o];self.assertEqual(len(ips),1)
        self.assertEqual(ips[0]['component'],out['ip_component']);self.assertEqual(set(ips[0]['addresses']),{'8.8.8.8','1.1.1.1'})
        self.assertEqual(ips[0]['protocol'],'tls')
        domains=[h for o in recipe['overrides']if o['protocol']=='tls'for h in o.get('domains',[])]
        self.assertIn('example.com',domains);self.assertIn('other.net',domains)
        rules=out['config']['NFQWS_ARGS_CUSTOM'].split(' --new ')
        ipindex=next(i for i,x in enumerate(rules)if '--ipset-ip='in x)
        self.assertTrue(all(i<ipindex for i,x in enumerate(rules)if '--hostlist-domains='in x))

    def test_no_sni_ip_rule_has_no_hostlist_filters_and_exclusion_pass_guards_precede_it(self):
        out=self.php("$r=NfqwsStrategySynthesis::forTargets($a,$manifest,$nativeHosts);echo json_encode(NfqwsStrategySynthesis::bind($r,$base));")
        self.assertNotIn('error',out);rules=out['NFQWS_ARGS_CUSTOM'].split(' --new ')
        self.assertIn('--hostlist=/tmp/exclude.list',rules[0]);self.assertIn('--lua-desync=pass',rules[0])
        self.assertNotIn('--hostlist-exclude=',rules[0]);self.assertNotIn('--hostlist-auto=',rules[0])
        self.assertIn('--hostlist-domains=t.me,telegram.org,telegram.me,telesco.pe',rules[1]);self.assertIn('--lua-desync=pass',rules[1])
        for rule in rules:
            if '--ipset-ip='in rule:
                self.assertNotIn('--hostlist',rule);self.assertIn('--filter-tcp=443',rule);self.assertIn('--filter-l7=tls',rule)
            elif rule not in rules[:2]:self.assertIn('--hostlist-exclude=/tmp/exclude.list',rule)

    def test_manifest_missing_drifted_pin_or_typed_claim_cannot_guide_assembly(self):
        for mutation in ["unset($observations[1]['custom_manifest']);", "$observations[1]['custom_manifest']['pins'][0]['address']='1.1.1.1';",
            "$observations[1]['custom_manifest']['targets'][0]['kind']='domain';", "$observations[1]['custom_manifest']['dns_context']=str_repeat('a',64);"]:
            with self.subTest(mutation=mutation):
                out=self.php(mutation+"NfqwsStrategySynthesis::assemble($observations);echo json_encode(['accepted'=>true]);")
                self.assertEqual(out,dict(error='incomparable_result'))

    def test_unscoped_or_differently_guarded_measured_recipe_cannot_claim_literal_evidence(self):
        for mutation in ["unset($observations[1]['recipe']['custom_scope']);$observations[1]['recipe']['overrides']=[];",
                         "$observations[1]['recipe']['custom_scope']['protected_domains']=['example.com'];$observations[1]['recipe']['overrides'][0]['domains']=['example.com'];"]:
            out=self.php(mutation+"NfqwsStrategySynthesis::assemble($observations);echo json_encode(['accepted'=>true]);")
            self.assertEqual(out,dict(error='incomparable_result'))

    def test_recipe_dropped_extra_private_duplicate_ip_or_missing_domain_shield_is_refused(self):
        mutations=["array_pop($r['overrides']);", "$r['overrides'][1]['addresses']=['9.9.9.9'];",
            "$r['overrides'][1]['addresses']=['127.0.0.1'];", "$r['overrides'][1]['addresses']=['8.8.8.8','8.8.8.8'];",
            "array_shift($r['overrides']);", "$r['custom_scope']['manifest_sha256']=str_repeat('a',64);",
            "$r['overrides'][1]['protocol']='quic';", "$r['overrides'][1]['domains']=['8.8.8.8'];",
            "$r['overrides']=array_reverse($r['overrides']);"]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                out=self.php("$r=NfqwsStrategySynthesis::forTargets($a,$manifest,$nativeHosts);"+mutation+"NfqwsStrategySynthesis::compile($r);echo json_encode(['accepted'=>true]);")
                self.assertEqual(out,dict(error='invalid_synthesis_recipe'))

    def test_rule_cap_counts_both_exclusion_guards_and_never_drops_an_ip(self):
        out=self.php("$out=[];foreach([3,4,24]as $cap){try{$r=NfqwsStrategySynthesis::assemble($observations,'all',$cap);$out[]=['count'=>count(explode(' --new ',NfqwsStrategySynthesis::bind($r,$base)['NFQWS_ARGS_CUSTOM'])),'recipe'=>$r];}catch(Throwable $e){$out[]=['error'=>$e->getMessage()];}}echo json_encode($out);")
        self.assertIsInstance(out,list,out);self.assertEqual(out[0],dict(error='synthesis_rule_limit'))
        self.assertEqual(out[1]['count'],4);self.assertEqual(out[2]['count'],4)
        boundary=self.php(r'''$r=NfqwsStrategySynthesis::forTargets($a,$manifest,array_map(static fn($i)=>'h'.$i.'.example.net',range(0,19)));
 $domain=$r['overrides'][0];$ip=$r['overrides'][1];$r['overrides']=[];
 foreach($domain['domains']as $host)$r['overrides'][]=['protocol'=>'tls','domains'=>[$host],'component'=>$domain['component']];
 $r['overrides'][]=$ip;$count=count(explode(' --new ',NfqwsStrategySynthesis::bind($r,$base)['NFQWS_ARGS_CUSTOM']));
 array_unshift($r['overrides'],$r['overrides'][0]);
 try{NfqwsStrategySynthesis::compile($r);$extra='accepted';}catch(Throwable $e){$extra=$e->getMessage();}
 echo json_encode(['exact24'=>$count,'twenty_fifth'=>$extra]);''')
        self.assertEqual(boundary,dict(exact24=24,twenty_fifth='invalid_synthesis_recipe'))

    def test_parent_child_grandchild_shadow_stays_before_destination_rule(self):
        out=self.php("$observations[]=$make($b,['child.example.com'],['8.8.8.8','1.1.1.1']);$observations[1]=$make($a,['example.com','grand.child.example.com','other.net'],['example.com']);$r=NfqwsStrategySynthesis::assemble($observations);echo json_encode($r);")
        self.assertNotIn('error',out);rows=out['overrides'];positions={d:i for i,o in enumerate(rows)if o['protocol']=='tls'for d in o.get('domains',[])}
        self.assertLess(positions['grand.child.example.com'],positions['child.example.com'])
        self.assertLess(positions['child.example.com'],positions['example.com'])
        self.assertLess(positions['example.com'],next(i for i,o in enumerate(rows)if 'addresses'in o))

    def test_old_domain_recipe_bytes_and_domain_only_scope_remain_unchanged(self):
        out=self.php("$old=NfqwsStrategySynthesis::compile($a);$domain=NfqwsStrategyPickerCustomWorker::prepareDocument(['example.com'],str_repeat('d',64));echo json_encode(['same'=>NfqwsStrategySynthesis::forTargets($a,$domain,$nativeHosts)===$a,'old'=>$old]);")
        self.assertNotIn('error',out);self.assertTrue(out['same']);self.assertEqual(out['old']['NFQWS_ARGS_CUSTOM'],'')

    def test_candidate_literal_parse_and_portable_native_arguments_preserve_ip_scope_order(self):
        out=self.php(r'''require_once dirname($argv[1],3).'/experimental/device-profiles/device-profiles-plan.php';
 $r=NfqwsStrategySynthesis::assemble($observations);$bound=NfqwsStrategySynthesis::bind($r,$base);
 $raw=NfqwsStrategyPickerConfig::candidate("KEEP=\"personal\"\nMODE_AUTO=\"--hostlist=/tmp/user.list --hostlist-auto=/tmp/auto.list --hostlist-exclude=/tmp/exclude.list\"\nNFQWS_EXTRA_ARGS=\"$MODE_AUTO\"\n",$bound);
 $parsed=AsusImportConfig::parse($raw);$args=NfqwsDeviceProfilesPlan::arguments($parsed,300);
 echo json_encode(['bound'=>$bound,'parsed'=>$parsed,'args'=>$args,'personal'=>str_contains($raw,'KEEP="personal"')]);'''.replace('$MODE_AUTO',r'\$MODE_AUTO'))
        self.assertNotIn('error',out);self.assertTrue(out['personal'])
        for key,value in out['bound'].items():self.assertEqual(out['parsed'][key],value)
        args=out['args'];ip=args.index('--ipset-ip=8.8.8.8,1.1.1.1')
        self.assertLess(args.index('--hostlist=/tmp/exclude.list'),ip)
        self.assertLess(args.index('--hostlist-domains=t.me,telegram.org,telegram.me,telesco.pe'),ip)
        self.assertEqual(args.count('--ipset-ip=8.8.8.8,1.1.1.1'),1)

    @unittest.skipUnless(os.environ.get('NFQWS_TEST_ENGINE_DIR'),'Requires pinned engine')
    def test_bound_program_expands_and_dry_runs_in_actual_pinned_native_engine(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory)
            for name,value in [('user','example.com\n'),('auto',''),('exclude','t.me\n')]:
                (root/(name+'.list')).write_text(value)
            out=self.php("$r=NfqwsStrategySynthesis::assemble($observations);$base['NFQWS_EXTRA_ARGS']="+json.dumps('--hostlist='+str(root/'user.list')+' --hostlist-auto='+str(root/'auto.list')+' --hostlist-exclude='+str(root/'exclude.list'))+";echo json_encode(NfqwsStrategySynthesis::bind($r,$base));")
            self.assertNotIn('error',out)
            common=(PUBLIC.parents[2]/'core/etc/init.d/common').read_text();function=re.search(r'^_startup_args\(\) \{.*?^\}',common,re.M|re.S).group()
            script='\n'.join(k+'='+shlex.quote(v)for k,v in out.items())+'\nLOG_LEVEL=0\nUSER=nobody\nNFQUEUE_NUM=300\n'+function+'\n_startup_args\n'
            expanded=subprocess.run(['/bin/sh'],input=script,text=True,capture_output=True,check=True).stdout
            engine=Path(os.environ['NFQWS_TEST_ENGINE_DIR'])
            # This unprivileged grammar fixture runs the exact expanded rule
            # sequence. Actual privilege dropping belongs to root fixtures;
            # passing --user=nobody here attempts forbidden initgroups().
            rules=[x for x in shlex.split(expanded)if not x.startswith('--user=')]
            args=[str(engine/'nfqws2-x86_64'),'--dry-run','--qnum=0','--lua-init=@'+str(engine/'lua/zapret-lib.lua'),'--lua-init=@'+str(engine/'lua/zapret-antidpi.lua')]+rules
            r=subprocess.run(args,capture_output=True,text=True,timeout=20)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            self.assertIn('--ipset-ip=8.8.8.8,1.1.1.1',expanded)
            self.assertEqual(expanded.count('--hostlist='+str(root/'exclude.list')),1)


if __name__=='__main__':unittest.main()
