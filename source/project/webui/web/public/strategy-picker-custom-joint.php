<?php
require_once __DIR__.'/strategy-picker-custom-samples.php';

/** Internal joint comparison; custom evidence is always re-derived from the
 * committed private artifacts. Native and OpenSSL root scores stay separate. */
final class NfqwsStrategyPickerCustomJoint
{
    public function __construct(private NfqwsStrategyPickerCustomSamples $samples,private string $id,private ?string $original=null){}
    private static function nativeTargets(array $runs):array
    {
        if(!array_is_list($runs)||!in_array(count($runs),[1,2],true))throw new RuntimeException('incomparable_result');
        $names=null;$target=null;
        foreach($runs as $run){
            if(!is_array($run)||!is_array($run['domains']??null)||!is_array($run['probe_hosts']??null)||
                !array_is_list($run['probe_hosts'])||!is_string($run['targets']??null)||
                !preg_match('/^[a-f0-9]{64}$/D',$run['targets']))throw new RuntimeException('incomparable_result');
            $scope=array_values(array_unique(array_merge(array_keys($run['domains']),$run['probe_hosts'])));
            if(!$scope||count($scope)>256)throw new RuntimeException('incomparable_result');
            foreach($scope as $host)if(!is_string($host)||NfqwsStrategySynthesis::host($host)===null)throw new RuntimeException('incomparable_result');
            if($names!==null&&($scope!==$names||$run['targets']!==$target))throw new RuntimeException('incomparable_result');
            $names=$scope;$target=$run['targets'];
        }
        return $names;
    }
    private function configuration(array $profile):void
    {
        if($this->original===null)return;
        try{
            $variant=$profile['variant']??null;
            if(strlen($this->original)>262144||!is_array($variant))throw new RuntimeException('incomparable_result');
            if(($profile['source']??null)==='synthesis'){
                if(!is_array($profile['components']??null)||NfqwsStrategySynthesis::bind($profile['components'],$variant)!==$variant)
                    throw new RuntimeException('incomparable_result');
                $manifest=$this->samples->manifestFor($this->id);
                if($manifest['schema_version']===2&&(!isset($profile['components']['custom_scope'])||
                    NfqwsStrategySynthesis::forTargets($profile['components'],$manifest,self::nativeTargets($profile['runs']??[]))!==$profile['components']))
                    throw new RuntimeException('incomparable_result');
            }
            $raw=NfqwsStrategyPickerConfig::candidate($this->original,$variant);
            if(hash('sha256',$raw)!==($profile['config_sha256']??null))throw new RuntimeException('incomparable_result');
        }catch(Throwable $e){throw new RuntimeException('incomparable_result',0,$e);}
    }
    private function evidence(array $profile,int $repeats=2):array
    {
        $this->configuration($profile);
        $role=$profile['custom_role']??null;$config=$profile['config_sha256']??null;
        if(!is_string($role)||!preg_match('/^[a-z0-9][a-z0-9_-]{0,63}$/D',$role)||
            !is_string($config)||!preg_match('/^[a-f0-9]{64}$/D',$config))throw new RuntimeException('incomparable_result');
        foreach(['runs','custom_runs']as $key)
            if(!is_array($profile[$key]??null)||!array_is_list($profile[$key])||count($profile[$key])!==$repeats)
                throw new RuntimeException('incomparable_result');
        $runs=[];
        foreach($profile['custom_runs']as $i=>$claimed){
            $sample=$claimed['sample_id']??null;
            if(!is_string($sample)||!preg_match('/^[a-f0-9]{32}$/D',$sample))throw new RuntimeException('incomparable_result');
            $actual=$this->samples->load($this->id,$sample);$document=$actual['document'];$score=$actual['score'];
            if($document['role']!==$role||$document['config_sha256']!==$config||$document['repeat']!==$i+1||
                $score!==$claimed||($profile['runs'][$i]['context_sha256']??null)!==$score['context_sha256'])
                throw new RuntimeException('incomparable_result');
            $runs[]=$score;
        }
        return $runs;
    }
    public function scopeRecipe(array $recipe,array $control):array
    {
        if(($control['source']??null)!=='current'||($control['sample_type']??null)!=='repeated')
            throw new RuntimeException('incomparable_result');
        $this->evidence($control);$manifest=$this->samples->manifestFor($this->id);
        return NfqwsStrategySynthesis::forTargets($recipe,$manifest,self::nativeTargets($control['runs']));
    }
    public function observation(array $profile):array
    {
        try{
            if($this->original===null||($profile['source']??null)!=='synthesis'||!is_array($profile['components']??null))
                throw new RuntimeException('incomparable_result');
            $count=match($profile['sample_type']??null){'exploratory'=>1,'repeated'=>2,default=>0};
            if($count===0)throw new RuntimeException('incomparable_result');
            $runs=$this->evidence($profile,$count);
            $out=['recipe'=>$profile['components'],'runs'=>$profile['runs'],'custom_runs'=>$runs];
            $manifest=$this->samples->manifestFor($this->id);
            if($manifest['schema_version']===2){
                $base=array_intersect_key($profile['components'],array_flip(['http','tls','quic']));$base['overrides']=[];
                if(NfqwsStrategySynthesis::forTargets($base,$manifest,self::nativeTargets($profile['runs']))!==$profile['components'])
                    throw new RuntimeException('incomparable_result');
                $out['custom_manifest']=$manifest;
            }elseif(($profile['components']['overrides']??[])!==[])throw new RuntimeException('incomparable_result');
            return $out;
        }catch(Throwable $e){throw new RuntimeException('incomparable_result',0,$e);}
    }
    public function compare(array $baseline,array $candidate,string $goal,bool $customOnly=false):array
    {
        $no=static fn($reason)=>['eligible'=>false,'reason'=>$reason,'gain'=>0];
        try{
            $a=$this->evidence($baseline);$b=$this->evidence($candidate);
            $native=NfqwsStrategyPickerScore::compare($baseline['runs'],$candidate['runs'],$goal);
            if(!in_array($native['reason'],['improved','no_improvement','goal_no_improvement'],true))return $no($native['reason']);
            // Fixed controls are safety measurements even in custom-only mode.
            // A gain elsewhere never pays for losing one of these protocols.
            foreach(['http','tls12','tls13','quic','tcp']as $protocol){
                $totals=[];$minimum=[];
                foreach([$baseline['runs'],$candidate['runs']]as $pair){
                    $values=[];
                    foreach($pair as $run){
                        $cell=$run['metrics'][$protocol]??null;
                        if(!is_array($cell)||!is_int($cell['ok']??null)||!is_int($cell['total']??null)||
                            $cell['total']<0||$cell['ok']<0||$cell['ok']>$cell['total'])throw new RuntimeException('incomparable_result');
                        $totals[]=$cell['total'];$values[]=$cell['ok'];
                    }
                    $minimum[]=min($values);
                }
                if(count(array_unique($totals))!==1)throw new RuntimeException('incomparable_result');
                if($minimum[1]<$minimum[0])return $no('native_regression');
            }
            $custom=NfqwsStrategyPickerCustomScore::compare($a,$b);
            if(!in_array($custom['reason'],['improved','no_improvement'],true))return $no($custom['reason']);
            $gain=$custom['gain']+($customOnly?0:$native['gain']);
            return ['eligible'=>$gain>0,'reason'=>$gain>0?'improved':'no_improvement','gain'=>$gain,
                'native'=>$native,'custom'=>$custom];
        }catch(Throwable $e){return $no('incomparable_result');}
    }
}
