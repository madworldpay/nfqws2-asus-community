<?php
declare(strict_types=1);
require_once __DIR__.'/ip-health-store.php';
require_once __DIR__.'/ip-health-probe.php';

/** One bounded worker iteration. At most three probes (nine seconds) per tick. */
final class NfqwsIpHealthController
{
    private NfqwsIpHealthProbe $probe;
    private const SNIS=['www.cloudflare.com','www.microsoft.com'];
    public function __construct(private NfqwsIpHealthStore $store,?NfqwsIpHealthProbe $probe=null){$this->probe=$probe??new NfqwsIpHealthProbe();}
    private static function validEvent(mixed $event,int $now):bool
    {
        if(!is_array($event)||count($event)!==5||!in_array($event['kind']??null,['silent','reply'],true)||!is_int($event['at']??null)||$event['at']>$now+2||$event['at']<$now-60||!is_string($event['ip']??null)||NfqwsIpHealthStore::publicIp($event['ip'])!==$event['ip']||!is_int($event['client_port']??null)||!is_string($event['host']??null))return false;
        return $event['kind']==='reply'?$event['client_port']===0&&$event['host']==='':$event['client_port']>=1&&$event['client_port']<=65535&&NfqwsIpHealthStore::host($event['host']);
    }
    public function tick(int $now,string $generation,string $interface,array $events):void
    {
        if(!NfqwsIpHealthStore::saneTime($now)||!NfqwsIpHealthStore::generation($generation)||!preg_match('/^[A-Za-z0-9_.:-]{1,15}$/D',$interface))return;
        $this->store->transaction(function(array &$v)use($generation){if($v['generation']!==$generation){$v['generation']=$generation;$v['recheck']=[];}},$now);
        $state=$this->store->view($now);if(!$state['enabled'])return;
        $candidate=$this->store->evidence(function(array &$ram)use($generation,$events,$now){
            if(($ram['schema_version']??null)!==1||($ram['generation']??null)!==$generation||!is_array($ram['candidates']??null))$ram=['schema_version'=>1,'generation'=>$generation,'candidates'=>[],'control_index'=>0];
            if(!in_array($ram['control_index']??null,[0,1],true))$ram['control_index']=0;
            foreach($ram['candidates'] as $ip=>$c)if(!is_array($c)||!is_int($c['at']??null)||$c['at']<$now-60||$c['at']>$now+2||!is_array($c['flows']??null)||!is_string($c['host']??null)||!NfqwsIpHealthStore::host($c['host'])||NfqwsIpHealthStore::publicIp((string)$ip)!==$ip)unset($ram['candidates'][$ip]);
            foreach(array_slice($events,0,512) as $event){if(!self::validEvent($event,$now))continue;$ip=$event['ip'];if($event['kind']==='reply'){unset($ram['candidates'][$ip]);continue;}$c=$ram['candidates'][$ip]??['host'=>$event['host'],'flows'=>[],'at'=>$event['at']];$c['flows'][(string)$event['client_port']]=$event['at'];$c['flows']=array_slice($c['flows'],-16,null,true);$c['at']=max($c['at'],$event['at']);$ram['candidates'][$ip]=$c;}
            $ram['candidates']=array_slice($ram['candidates'],-512,null,true);
            foreach($ram['candidates'] as $ip=>$c){$flows=array_filter($c['flows'],fn($at)=>is_int($at)&&$at>=$now-60&&$at<=$now+2);if(count($flows)>=2){unset($ram['candidates'][$ip]);$control=['1.1.1.1','1.0.0.1'][$ram['control_index']];$ram['control_index']=1-$ram['control_index'];return ['ip'=>$ip,'host'=>$c['host'],'control'=>$control];}}return null;
        });
        // Ordinary retests consume one probe. A queued manual recheck of a
        // suspended network requires a fresh control and both neutral SNIs.
        // Explicit requests precede automatic work. Pick the oldest check
        // next so a slow, full list cannot repeatedly favor its first entries.
        $queuedIds=array_fill_keys($state['recheck'],true);$entries=$state['entries'];
        uasort($entries,static function(array $a,array $b)use($queuedIds):int{
            $priority=(int)isset($queuedIds[$b['id']])-(int)isset($queuedIds[$a['id']]);
            return $priority?:(($a['last_check']??$a['first_seen'])<=>($b['last_check']??$b['first_seen']));
        });
        foreach($entries as $id=>$entry){$queued=in_array($id,$state['recheck'],true);$suspended=$entry['generation']!==$generation;if($suspended&&!$queued)continue;if(!$queued&&($entry['last_check']??$entry['first_seen'])>$now-900)continue;
            if($suspended){$answer='unknown';if($this->probe->check('1.1.1.1',self::SNIS[0],$interface)==='replied'){$answer=$this->probe->check($entry['ip'],self::SNIS[0],$interface);if($answer==='silent'){$second=$this->probe->check($entry['ip'],self::SNIS[1],$interface);$answer=$second==='silent'?'silent':($second==='replied'?'replied':'unknown');}}}
            else $answer=$this->probe->check($entry['ip'],self::SNIS[0],$interface);
            $this->store->transaction(function(array &$v)use($id,$entry,$answer,$now,$generation,$suspended){if(!$v['enabled']||$v['generation']!==$generation||($v['entries'][$id]??null)!==$entry)return;$v['recheck']=array_values(array_diff($v['recheck'],[$id]));$e=&$v['entries'][$id];$e['last_check']=$now;$e['check_state']=in_array($answer,['silent','replied'],true)?$answer:'unknown';$e['successes']=$answer==='replied'?$e['successes']+1:0;if($suspended&&$answer==='silent')$e['generation']=$generation;if($e['successes']>=3)unset($v['entries'][$id]);},$now);return;
        }
        if($candidate===null)return;$id=substr(hash('sha256',$candidate['ip']),0,32);$old=$state['entries'][$id]??null;if($old!==null&&$old['generation']===$generation)return;
        // Never interpret failed controls as destination-specific failure.
        $control=$this->probe->check($candidate['control'],self::SNIS[0],$interface);if($control!=='replied')return;
        $first=$this->probe->check($candidate['ip'],self::SNIS[0],$interface);if($first!=='silent')return;
        $second=$this->probe->check($candidate['ip'],self::SNIS[1],$interface);if($second!=='silent')return;
        $this->store->transaction(function(array &$v)use($id,$candidate,$now,$generation,$old,$state){if(!$v['enabled']||$v['generation']!==$generation||($v['entries'][$id]??null)!==$old||$v['history']!==$state['history'])return;
            if($old!==null){$v['entries'][$id]=array_replace($old,['last_check'=>$now,'check_state'=>'silent','generation'=>$generation,'successes'=>0]);return;}
            $repeat=isset($v['history'][$candidate['ip']])&&$v['history'][$candidate['ip']]>=$now-2592000&&$v['history'][$candidate['ip']]<=$now+5;$v['entries'][$id]=['id'=>$id,'ip'=>$candidate['ip'],'port'=>443,'host'=>$candidate['host'],'until'=>$now+($repeat?604800:86400),'first_seen'=>$now,'incident'=>$repeat?2:1,'last_check'=>$now,'check_state'=>'silent','generation'=>$generation,'successes'=>0];$v['history'][$candidate['ip']]=$now;},$now);
    }
}
