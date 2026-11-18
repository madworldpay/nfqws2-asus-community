"""Assembly preserves custom/native scope, suffix ordering and rule closure."""
import json
import subprocess
import unittest
from test_dpi_normalize import PHP, PUBLIC


SETUP=r'''
require $argv[1].'/strategy-picker-custom-score.php';
$m=NfqwsStrategySynthesis::matrix(['max_repeats'=>4]);
$a=$m['initial'][0];$b=$m['initial'][1];$c=$m['initial'][4];$blank=NfqwsStrategySynthesis::blank();
function fixtureNative($hosts,$tls=[],$http=[]){
 $metrics=array_fill_keys(['http','tls12','tls13','quic'],['ok'=>0,'total'=>count($hosts)]);
 $metrics['tcp']=['ok'=>0,'total'=>1];$rows=[];
 foreach($hosts as $host){$rows[$host]=['http'=>in_array($host,$http,true),'tls12'=>in_array($host,$tls,true),
  'tls13'=>in_array($host,$tls,true),'quic'=>false];foreach($rows[$host]as $p=>$ok)if($ok)$metrics[$p]['ok']++;}
 return ['targets'=>str_repeat('a',64),'context_sha256'=>str_repeat('d',64),'metrics'=>$metrics,'domains'=>$rows];
}
function fixtureCustom($hosts,$ok){
 static $id=0;$rows=[];
 foreach($hosts as $host)foreach(['tls12','tls13']as $tls){$response=AsusDpiSiteCheck::response('response');
  $response['http_status']=in_array($host,$ok,true)?200:403;$rows[]=['host'=>$host,'tls'=>$tls,'response'=>$response];}
 return NfqwsStrategyPickerCustomScore::measure(['schema_version'=>1,'hosts'=>$hosts,'dns_context'=>str_repeat('c',64),
  'manifest_sha256'=>str_repeat('b',64),'fingerprint'=>AsusDpiSiteCheckProbe::PINNED_FINGERPRINT,'observations'=>$rows],
  str_repeat('d',64),str_pad(dechex(++$id),32,'0',STR_PAD_LEFT));
}
function fixtureObservation($recipe,$native,$customHosts=null,$customOK=[],$repeats=1){
 $o=['recipe'=>$recipe,'runs'=>array_fill(0,$repeats,$native)];
 if($customHosts!==null){$o['custom_runs']=[];for($i=0;$i<$repeats;$i++)$o['custom_runs'][]=fixtureCustom($customHosts,$customOK);}
 return $o;
}
function fixtureEffective($recipe,$host,$protocol='tls'){
 foreach($recipe['overrides']as $o)if($o['protocol']===$protocol)foreach($o['domains']as $domain)
  if($host===$domain||str_ends_with($host,'.'.$domain))return $o['component'];
 return $recipe[$protocol];
}
$hosts=['www.youtube.com','one.example.net','two.example.net'];$zero=fixtureNative($hosts);
'''


class CustomAssemblyTests(unittest.TestCase):
    def php(self, body):
        r=subprocess.run([PHP,'-n','-r',SETUP+body,str(PUBLIC)],capture_output=True,text=True,timeout=8)
        self.assertEqual(r.returncode,0,r.stderr+r.stdout)
        self.assertEqual(r.stderr,'')
        return json.loads(r.stdout)

    def test_custom_only_exploration_selects_measured_custom_tls_instead_of_pass(self):
        r=self.php(r'''
        $custom=['site.example.com'];$o=[fixtureObservation($blank,$zero,$custom,[],2),
          fixtureObservation($a,$zero,$custom,$custom)];
        $result=NfqwsStrategySynthesis::assemble($o,'all',24,true);
        echo json_encode([fixtureEffective($result,$custom[0]),$a['tls']]);
        ''')
        self.assertEqual(r[0],r[1])

    def test_joint_scope_combines_complementary_fixed_and_custom_winners(self):
        r=self.php(r'''
        $custom=['site.example.com'];$o=[fixtureObservation($blank,$zero,$custom,[],2),
          fixtureObservation($a,fixtureNative($hosts,['www.youtube.com']),$custom,[]),
          fixtureObservation($b,$zero,$custom,$custom)];
        $result=NfqwsStrategySynthesis::assemble($o,'youtube');
        echo json_encode([fixtureEffective($result,'www.youtube.com')===$a['tls'],
          fixtureEffective($result,$custom[0])===$b['tls']]);
        ''')
        self.assertEqual(r,[True,True])

    def test_idna_top_level_domain_is_retained_in_the_generated_host_scope(self):
        r=self.php(r'''
        $custom=['xn--e1afmkfd.xn--p1ai'];$o=[fixtureObservation($blank,$zero,$custom,[],2),
          fixtureObservation($c,fixtureNative($hosts,$hosts),$custom,[]),fixtureObservation($a,$zero,$custom,$custom)];
        $result=NfqwsStrategySynthesis::assemble($o);
        echo json_encode([NfqwsStrategySynthesis::domain($custom[0]),
          fixtureEffective($result,$custom[0])===$a['tls'],NfqwsStrategySynthesis::compile($result)]);
        ''')
        self.assertTrue(r[0])
        self.assertTrue(r[1])
        self.assertIn('--hostlist-domains=xn--e1afmkfd.xn--p1ai',r[2]['NFQWS_ARGS_CUSTOM'])

    def test_custom_parent_cannot_shadow_a_native_child_using_the_general_component(self):
        r=self.php(r'''
        $hosts[]='child.example.com';$zero=fixtureNative($hosts);$custom=['example.com'];
        $o=[fixtureObservation($blank,$zero,$custom,[],2),
          fixtureObservation($a,fixtureNative($hosts,$hosts),$custom,[]),fixtureObservation($b,$zero,$custom,$custom)];
        $result=NfqwsStrategySynthesis::assemble($o);
        echo json_encode(['rules'=>$result['overrides'],'child'=>fixtureEffective($result,'child.example.com')===$a['tls'],
          'parent'=>fixtureEffective($result,'example.com')===$b['tls']]);
        ''')
        self.assertTrue(r['child'])
        self.assertTrue(r['parent'])
        child=next(i for i,x in enumerate(r['rules'])if 'child.example.com'in x['domains'])
        parent=next(i for i,x in enumerate(r['rules'])if 'example.com'in x['domains'])
        self.assertLess(child,parent)

    def nested(self, final):
        return self.php(r'''
        $custom=['example.com','child.example.com','grand.child.example.com'];
        $o=[fixtureObservation($blank,$zero,$custom,[],2),fixtureObservation($c,fixtureNative($hosts,$hosts),$custom,[]),
          fixtureObservation($a,$zero,$custom,[$custom[0],$custom[2]]),fixtureObservation($b,$zero,$custom,[$custom[1]])];
        '''+final)

    def test_grouping_cannot_merge_a_parent_and_grandchild_across_a_different_child_rule(self):
        r=self.nested(r'''
        $result=NfqwsStrategySynthesis::assemble($o);$rules=array_values(array_filter($result['overrides'],fn($v)=>$v['protocol']==='tls'));
        echo json_encode(['rules'=>$rules,'effective'=>[fixtureEffective($result,$custom[0])===$a['tls'],
          fixtureEffective($result,$custom[1])===$b['tls'],fixtureEffective($result,$custom[2])===$a['tls']]]);
        ''')
        self.assertEqual(r['effective'],[True,True,True])
        self.assertEqual(len(r['rules']),3)
        self.assertIn('grand.child.example.com',r['rules'][0]['domains'])
        self.assertIn('child.example.com',r['rules'][1]['domains'])
        self.assertIn('example.com',r['rules'][2]['domains'])

    def test_rule_cap_fails_closed_instead_of_silently_dropping_a_required_target(self):
        r=self.nested(r'''
        try{NfqwsStrategySynthesis::assemble($o,'all',2);$out='accepted';}
        catch(Throwable $e){$out=$e->getMessage();}echo json_encode($out);
        ''')
        self.assertEqual(r,'synthesis_rule_limit')

    def test_unrelated_equal_components_share_one_rule_without_losing_scope(self):
        r=self.php(r'''
        $hosts=array_merge($hosts,['three.example.net','four.example.net','five.example.net']);$zero=fixtureNative($hosts);
        $custom=['alpha.example.com','beta.example.com','delta.example.com','epsilon.example.com','gamma.example.com'];
        $o=[fixtureObservation($blank,$zero,$custom,[],2),fixtureObservation($c,fixtureNative($hosts,$hosts),$custom,[]),
          fixtureObservation($a,$zero,$custom,$custom)];$result=NfqwsStrategySynthesis::assemble($o,'all',1);
        echo json_encode(['rules'=>$result['overrides'],'effective'=>array_map(fn($h)=>fixtureEffective($result,$h)===$a['tls'],$custom)]);
        ''')
        self.assertEqual(len(r['rules']),1)
        self.assertEqual(len(r['rules'][0]['domains']),5)
        self.assertTrue(all(r['effective']))

    def test_incomplete_or_changed_custom_evidence_is_not_silently_ignored(self):
        for mutation in ["unset($o[1]['custom_runs']);","$o[1]['custom_runs']=[];",
                         "$o[1]['custom_runs'][0]['fingerprint']='forged';",
                         "$o[1]['custom_runs']=[fixtureCustom(['other.example.com'],[])];"]:
            with self.subTest(mutation=mutation):
                r=self.php(r'''
                $custom=['site.example.com'];$o=[fixtureObservation($blank,$zero,$custom,[],2),fixtureObservation($a,$zero,$custom,$custom)];
                '''+mutation+r'''
                try{NfqwsStrategySynthesis::assemble($o);$out='accepted';}catch(Throwable $e){$out=$e->getMessage();}
                echo json_encode($out);
                ''')
                self.assertEqual(r,'incomparable_result')

    def test_native_only_rule_cap_also_refuses_partial_scope(self):
        r=self.php(r'''
        $hosts=array_merge($hosts,['a.example.com','b.example.com']);$zero=fixtureNative($hosts);
        $o=[fixtureObservation($blank,$zero,null,[],2),fixtureObservation($c,fixtureNative($hosts,array_slice($hosts,0,3))),
          fixtureObservation($a,fixtureNative($hosts,['a.example.com'])),fixtureObservation($b,fixtureNative($hosts,['b.example.com']))];
        try{NfqwsStrategySynthesis::assemble($o,'all',1);$out='accepted';}catch(Throwable $e){$out=$e->getMessage();}
        echo json_encode($out);
        ''')
        self.assertEqual(r,'synthesis_rule_limit')

    def test_refinement_continues_when_a_full_exception_set_exceeds_the_final_cap(self):
        r=self.php(r'''
        $hosts=[];for($i=0;$i<15;$i++)$hosts[]='h'.$i.'.example.com';$zero=fixtureNative($hosts);
        $o=[fixtureObservation($blank,$zero,null,[],2)];
        for($i=0;$i<15;$i++){
          $component=['method'=>'multisplit','pos'=>['2','1,midsld','midsld','host+1','sniext+1'][$i%5],
            'fake'=>true,'fooling'=>['seq','ack','md5'][intdiv($i,5)],'repeats'=>1];
          $recipe=['http'=>$component,'tls'=>$component,'quic'=>['method'=>'pass'],'overrides'=>[]];
          $o[]=fixtureObservation($recipe,fixtureNative($hosts,[$hosts[$i]],[$hosts[$i]]));
        }
        try{NfqwsStrategySynthesis::assemble($o);$error=null;}catch(Throwable $e){$error=$e->getMessage();}
        $next=NfqwsStrategySynthesis::refine($o,['max_repeats'=>4]);echo json_encode(['assembly'=>$error,'next'=>count($next)]);
        ''')
        self.assertEqual(r['assembly'],'synthesis_rule_limit')
        self.assertGreater(r['next'],0)


if __name__=='__main__':unittest.main()
