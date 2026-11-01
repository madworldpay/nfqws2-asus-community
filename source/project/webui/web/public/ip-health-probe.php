<?php
declare(strict_types=1);
require_once __DIR__.'/ip-health-store.php';

/** Numeric-IP TLS reachability. No name resolution and no OpenSSL subprocess. */
class NfqwsIpHealthProbe
{
    /** Check the required local capabilities before publishing any active ban. */
    public function availability(string $interface):bool
    {
        if(!function_exists('socket_create')||!preg_match('/^[A-Za-z0-9_.:-]{0,15}$/D',$interface))return false;$socket=null;
        try{$socket=@socket_create(AF_INET,SOCK_STREAM,SOL_TCP);return $socket!==false&&$this->prepareSocket($socket,$interface);}
        catch(Throwable $e){return false;}finally{if($socket!==null&&$socket!==false)@socket_close($socket);}
    }
    public function check(string $ip,string $sni,string $interface):string
    {
        $canonical=NfqwsIpHealthStore::publicIp($ip);if($canonical===null||!NfqwsIpHealthStore::host($sni)||!preg_match('/^[A-Za-z0-9_.:-]{0,15}$/D',$interface))return 'unknown';
        return $this->exchange($canonical,$sni,$interface,443);
    }
    public static function clientHello(string $sni):string
    {
        if(!NfqwsIpHealthStore::host($sni))throw new RuntimeException('invalid_request');
        $name="\x00".pack('n',strlen($sni)).$sni;$sniExtension=pack('n',strlen($name)).$name;
        $extensions="\x00\x00".pack('n',strlen($sniExtension)).$sniExtension.
            "\x00\x0a\x00\x06\x00\x04\x00\x1d\x00\x17".
            "\x00\x0b\x00\x02\x01\x00".
            "\x00\x0d\x00\x0a\x00\x08\x04\x03\x08\x04\x04\x01\x02\x01";
        $body="\x03\x03".random_bytes(32)."\x00\x00\x08\xc0\x2f\xc0\x2b\x00\x9c\x00\x2f\x01\x00".pack('n',strlen($extensions)).$extensions;
        $hello="\x01".substr(pack('N',strlen($body)),1).$body;return "\x16\x03\x01".pack('n',strlen($hello)).$hello;
    }
    /** Linux UAPI asm-generic/socket.h: SO_MARK=36, SO_BINDTODEVICE=25. */
    protected function prepareSocket(mixed $socket,string $interface):bool
    {
        if(!@socket_set_option($socket,SOL_SOCKET,defined('SO_MARK')?constant('SO_MARK'):36,0x40000000))return false;
        return $interface===''||@socket_set_option($socket,SOL_SOCKET,defined('SO_BINDTODEVICE')?constant('SO_BINDTODEVICE'):25,$interface."\0");
    }
    protected function exchange(string $ip,string $sni,string $interface,int $port):string
    {
        if(!function_exists('socket_create'))return 'unknown';$socket=null;
        try{$socket=@socket_create(str_contains($ip,':')?AF_INET6:AF_INET,SOCK_STREAM,SOL_TCP);if($socket===false)return 'unknown';if(!$this->prepareSocket($socket,$interface)||!@socket_set_nonblock($socket))return 'unknown';
            // hrtime(true) is a float on 32-bit router PHP. Keep deadlines in
            // seconds, converting only bounded select arguments to integers.
            $deadline=hrtime(true)/1000000000+3.0;$connected=@socket_connect($socket,$ip,$port);
            if(!$connected){$error=socket_last_error($socket);if(!in_array($error,[SOCKET_EINPROGRESS,SOCKET_EALREADY,SOCKET_EWOULDBLOCK],true))return 'unknown';$r=[];$w=[$socket];$e=[$socket];$selected=@socket_select($r,$w,$e,1,0);if($selected===false||$selected===0||@socket_get_option($socket,SOL_SOCKET,SO_ERROR)!==0)return 'unknown';}
            $hello=self::clientHello($sni);$offset=0;
            while($offset<strlen($hello)){$left=$deadline-hrtime(true)/1000000000;if($left<=0)return 'unknown';$seconds=(int)$left;$r=[];$w=[$socket];$e=[$socket];$n=@socket_select($r,$w,$e,$seconds,(int)(($left-$seconds)*1000000));if(!$n)return 'unknown';$sent=@socket_write($socket,substr($hello,$offset));if($sent===false||$sent===0)return 'replied';$offset+=$sent;}
            $left=$deadline-hrtime(true)/1000000000;if($left<=0)return 'unknown';$seconds=(int)$left;$r=[$socket];$w=[];$e=[$socket];$n=@socket_select($r,$w,$e,$seconds,(int)(($left-$seconds)*1000000));if($n===false)return 'unknown';if($n===0)return 'silent';
            // EOF, reset, alert and any payload are evidence against silence.
            $buf='';@socket_recv($socket,$buf,1,0);return 'replied';
        }catch(Throwable $e){return 'unknown';}finally{if($socket!==null&&$socket!==false)@socket_close($socket);}
    }
}
