<?php
/** Recognize only firewall4's standard offload hook or this application's hook.
 * Operator UCI settings and the existing flowtable/hardware flags stay intact.
 */
final class NfqwsNativeFlow
{
    public const OWNER='NFQWS2 native OpenWrt';
    public const HOOK_OWNER='NFQWS2 native OpenWrt flow control';
    private const CHAINS=['nfqws2_flow','nfqws2_flow_scope','nfqws2_flow_add'];
    public static function inspect(array $document): array
    {
        $nodes=$document['nftables']??null;
        if(!is_array($nodes)||!array_is_list($nodes)||count($nodes)>16384)throw new RuntimeException('invalid_firewall_snapshot');
        $flowtable=false;$definition='';$owned=[];$hooks=[];
        foreach($nodes as $node) {
            if(!is_array($node))throw new RuntimeException('invalid_firewall_snapshot');
            $ft=$node['flowtable']??null;
            if(is_array($ft)&&($ft['family']??null)==='inet'&&($ft['table']??null)==='fw4'&&($ft['name']??null)==='ft') {
                if($flowtable||($ft['hook']??null)!=='ingress'||($ft['prio']??null)!==0)throw new RuntimeException('custom_acceleration_rule');
                $devices=$ft['dev']??[];if(is_string($devices))$devices=[$devices];
                if(!is_array($devices)||!array_is_list($devices)||!$devices||count($devices)>128)throw new RuntimeException('custom_acceleration_rule');
                foreach($devices as $device)if(!is_string($device)||!preg_match('/^[a-zA-Z0-9_.:-]{1,15}$/D',$device))throw new RuntimeException('custom_acceleration_rule');
                $flags=$ft['flags']??[];if($flags!==[]&&$flags!==['offload'])throw new RuntimeException('custom_acceleration_rule');
                $definition='add flowtable inet fw4 ft { hook ingress priority 0; devices = { '.implode(', ',array_map(fn($v)=>'"'.$v.'"',$devices)).' }; counter;'.($flags?' flags offload;':'').' }';
                $flowtable=true;
            }
            $chain=$node['chain']??null;
            if(is_array($chain)&&($chain['family']??null)==='inet'&&($chain['table']??null)==='fw4'&&in_array($chain['name']??null,self::CHAINS,true)) {
                if(($chain['comment']??null)!==self::OWNER||isset($chain['hook']))throw new RuntimeException('flow_owner_conflict');
                $owned[$chain['name']]=true;
            }
            $rule=$node['rule']??null;
            if(!is_array($rule)||($rule['family']??null)!=='inet'||($rule['table']??null)!=='fw4')continue;
            $expr=$rule['expr']??null;if(!is_array($expr)||!array_is_list($expr))throw new RuntimeException('invalid_firewall_snapshot');
            $flows=array_filter($expr,fn($e)=>is_array($e)&&isset($e['flow']));
            $jumps=array_filter($expr,fn($e)=>is_array($e)&&in_array($e['jump']['target']??null,self::CHAINS,true));
            if(!$flows&&!$jumps)continue;
            if(in_array($rule['chain']??null,self::CHAINS,true))continue;
            $handle=$rule['handle']??null;
            if(($rule['chain']??null)!=='forward'||!is_int($handle)||$handle<1)throw new RuntimeException('flow_owner_conflict');
            if($flows) {
                $match=['match'=>['op'=>'==','left'=>['meta'=>['key'=>'l4proto']],'right'=>['set'=>['tcp','udp']]]];
                if($expr!==[$match,['flow'=>['op'=>'add','flowtable'=>'@ft']]])throw new RuntimeException('custom_acceleration_rule');
                $hooks[]=['state'=>'system','handle'=>$handle];
            }else {
                if($expr!==[['jump'=>['target'=>'nfqws2_flow']]]||($rule['comment']??null)!==self::HOOK_OWNER)throw new RuntimeException('flow_owner_conflict');
                $hooks[]=['state'=>'managed','handle'=>$handle];
            }
        }
        if(!$flowtable) {
            if($hooks||$owned)throw new RuntimeException('flow_owner_conflict');
            return ['state'=>'none','handle'=>null,'definition'=>''];
        }
        if(count($hooks)!==1)throw new RuntimeException('custom_acceleration_rule');
        $hook=$hooks[0];
        if(($hook['state']==='managed'&&count($owned)!==3)||($hook['state']==='system'&&$owned))throw new RuntimeException('flow_owner_conflict');
        return $hook+['definition'=>$definition];
    }
}
