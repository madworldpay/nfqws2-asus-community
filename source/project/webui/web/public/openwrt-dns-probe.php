<?php
/** Bounded, correlated DNS queries. No system resolver, shell or external helper. */
final class NfqwsOpenWrtDnsProbe
{
    private static function failure(string $reason,int $rcode=-1,bool $truncated=false):array
    {return ['ok'=>false,'rcode'=>$rcode,'truncated'=>$truncated,'answers'=>[],'reason'=>$reason];}
    private static function name(string $packet,int &$offset):string
    {
        $name=[];$at=$offset;$end=null;$seen=[];
        for($n=0;$n<128;$n++){
            if($at>=strlen($packet)||isset($seen[$at]))throw new RuntimeException('invalid_response');$seen[$at]=true;$size=ord($packet[$at++]);
            if(($size&0xc0)===0xc0){
                if($at>=strlen($packet))throw new RuntimeException('invalid_response');$next=(($size&0x3f)<<8)|ord($packet[$at++]);
                $end??=$at;if($next>=$at-2)throw new RuntimeException('invalid_response');$at=$next;continue;
            }
            if($size>63||$at+$size>strlen($packet))throw new RuntimeException('invalid_response');
            if($size===0){$offset=$end??$at;$value=strtolower(implode('.',$name));if(strlen($value)>253)throw new RuntimeException('invalid_response');return $value;}
            $name[]=substr($packet,$at,$size);$at+=$size;
        }
        throw new RuntimeException('invalid_response');
    }
    private static function parse(string $packet,int $id,string $name,int $type):array
    {
        if(strlen($packet)<12||strlen($packet)>4096)throw new RuntimeException('invalid_response');
        $h=unpack('nid/nflags/nqd/nan/nns/nar',substr($packet,0,12));$rcode=$h['flags']&15;$tc=(bool)($h['flags']&0x200);
        if($h['id']!==$id||($h['flags']&0xf800)!==0x8000||$h['qd']!==1||$h['an']>64||$h['an']+$h['ns']+$h['ar']>192)throw new RuntimeException('invalid_response');
        $at=12;$question=self::name($packet,$at);
        if($at+4>strlen($packet)||$question!==$name||substr($packet,$at,4)!==pack('nn',$type,1))throw new RuntimeException('invalid_response');$at+=4;
        if($tc)return self::failure('truncated',$rcode,true);if($rcode!==0)return self::failure('rcode',$rcode);
        $addresses=[];$aliases=[];
        for($i=0;$i<$h['an']+$h['ns']+$h['ar'];$i++){
            $owner=self::name($packet,$at);if($at+10>strlen($packet))throw new RuntimeException('invalid_response');
            $rr=unpack('ntype/nclass/Nttl/nsize',substr($packet,$at,10));$at+=10;$end=$at+$rr['size'];if($end>strlen($packet))throw new RuntimeException('invalid_response');
            if($i<$h['an']&&$rr['class']===1){
                if($rr['type']===5){$cursor=$at;$target=self::name($packet,$cursor);if($cursor!==$end)throw new RuntimeException('invalid_response');$aliases[$owner]=$target;}
                elseif($rr['type']===$type){if($rr['size']!==($type===1?4:16))throw new RuntimeException('invalid_response');$addresses[]=[$owner,inet_ntop(substr($packet,$at,$rr['size']))];}
            }
            $at=$end;
        }
        if($at!==strlen($packet))throw new RuntimeException('invalid_response');$allowed=[$name=>true];$next=$name;
        for($i=0;isset($aliases[$next]);$i++){$next=$aliases[$next];if($i>=16||isset($allowed[$next]))throw new RuntimeException('invalid_response');$allowed[$next]=true;}
        $answers=[];foreach($addresses as [$owner,$ip])if(isset($allowed[$owner]))$answers[]=$ip;
        $answers=array_values(array_unique($answers));return $answers?['ok'=>true,'rcode'=>0,'truncated'=>false,'answers'=>$answers,'reason'=>'ready']:self::failure('no_address',0);
    }
    private static function read($stream,int $length,float $deadline):string
    {
        $raw='';while(strlen($raw)<$length){$remaining=$deadline-microtime(true);if($remaining<=0)throw new RuntimeException('timed_out');
            stream_set_timeout($stream,(int)$remaining,(int)(($remaining-(int)$remaining)*1e6));$part=@fread($stream,$length-strlen($raw));
            if(!is_string($part)||$part==='')throw new RuntimeException('timed_out');$raw.=$part;
        }return $raw;
    }
    public static function query(string $address,int $port,string $name,string $type='A',string $transport='udp',int $timeout=2500):array
    {
        if(@inet_pton($address)===false||$port<1||$port>65535||!in_array($type,['A','AAAA'],true)||!in_array($transport,['udp','tcp'],true)||$timeout<1||$timeout>2500||strlen($name)>253||!preg_match('/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*$/D',$name))return self::failure('invalid_arguments');
        $id=random_int(0,65535);$question='';foreach(explode('.',$name)as $label)$question.=chr(strlen($label)).$label;
        $question.="\0".pack('nn',$type==='A'?1:28,1);$query=pack('nnnnnn',$id,0x100,1,0,0,0).$question;
        $deadline=microtime(true)+$timeout/1000;$target=str_contains($address,':')?'['.$address.']':$address;$stream=null;
        try{
            $stream=@stream_socket_client($transport.'://'.$target.':'.$port,$errno,$error,$timeout/1000,STREAM_CLIENT_CONNECT);
            if(!is_resource($stream))return self::failure('timed_out');$request=$transport==='tcp'?pack('n',strlen($query)).$query:$query;
            stream_set_timeout($stream,intdiv($timeout,1000),($timeout%1000)*1000);
            if(@fwrite($stream,$request)!==strlen($request))throw new RuntimeException('timed_out');
            if($transport==='tcp'){$length=unpack('n',self::read($stream,2,$deadline))[1];if($length<12||$length>4096)throw new RuntimeException('invalid_response');$packet=self::read($stream,$length,$deadline);}
            else{$packet=@fread($stream,4097);if(!is_string($packet)||$packet==='')throw new RuntimeException('timed_out');}
            return self::parse($packet,$id,$name,$type==='A'?1:28);
        }catch(Throwable $e){return self::failure($e->getMessage()==='timed_out'?'timed_out':'invalid_response');}
        finally{if(is_resource($stream))fclose($stream);}
    }
}
