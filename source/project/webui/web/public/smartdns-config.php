<?php
require_once __DIR__.'/share-read.php';

/** Bounded dnsmasq data includes. Never evaluates scripts or edits sources. */
final class AsusSmartDnsConfig
{
    public static function includePath(string $line): string
    {
        $value=preg_replace('/^[^=]*=[ \t]*/','',$line);
        if (str_contains($value,'\\')) throw new RuntimeException('existing_dns_rules');
        if (str_starts_with($value,'"')) {
            if (!preg_match('/^"([^"]*)"(?:[ \t\r]*|[ \t\r]+#.*)$/D',$value,$m)) throw new RuntimeException('existing_dns_rules');
            $path=$m[1];
        } else {
            $path=preg_replace('/[ \t\r]+#.*/','',$value);$path=rtrim($path," \t\r");
        }
        if (strlen($path)>1024 || !preg_match('~^/[A-Za-z0-9_.+/ -]+$~D',$path) ||
            preg_match('~//|/\.{1,2}(?:/|$)~',$path)) throw new RuntimeException('existing_dns_rules');
        return $path;
    }
    private static function walk(string $text,callable $reader): array
    {
        $files=[];$active=[];$scanned=strlen($text);$visited=0;$output='';
        $append=function(string $value)use(&$output){
            if (strlen($output)+strlen($value)>262144) throw new RuntimeException('existing_dns_rules');
            $output.=$value;
        };
        $visit=function(string $body,int $depth)use(&$visit,&$files,&$active,&$scanned,&$visited,$reader,$append){
            if ($depth>8 || strlen($body)>262144 || str_contains($body,"\0")) throw new RuntimeException('existing_dns_rules');
            foreach (explode("\n",rtrim($body,"\n")) as $raw) {
                $visited+=strlen($raw)+1;
                if ($visited>1048576) throw new RuntimeException('existing_dns_rules');
                $line=trim($raw);
                if (preg_match('/^(conf-dir|conf-script)\s*(?:=|$)/',$line)) throw new RuntimeException('existing_dns_rules');
                if (!preg_match('/^conf-file\s*(?:=|$)/',$line)) {$append($raw."\n");continue;}
                if (!preg_match('/^conf-file\s*=/',$line)) throw new RuntimeException('existing_dns_rules');
                $path=self::includePath($line);
                if (isset($active[$path])) throw new RuntimeException('existing_dns_rules');
                if (!isset($files[$path])) {
                    if (count($files)>=31) throw new RuntimeException('existing_dns_rules');
                    $entry=$reader($path);
                    if (!is_array($entry) || !is_string($entry['value']??null)) throw new RuntimeException('existing_dns_rules');
                    $scanned+=strlen($entry['value']);
                    if ($scanned>1048576) throw new RuntimeException('existing_dns_rules');
                    $files[$path]=$entry;
                }
                $active[$path]=true;$visit($files[$path]['value'],$depth+1);unset($active[$path]);
            }
        };
        $visit($text,1);
        return ['text'=>$output,'files'=>$files];
    }
    public static function expand(string $text,array $files): string
    {
        return self::walk($text,static function($path)use($files){
            if (!is_string($files[$path]??null)) throw new RuntimeException('existing_dns_rules');
            return ['value'=>$files[$path]];
        })['text'];
    }
    private static function read(string $path,int $owner): array
    {
        $canonical=$path;$boundary=null;$alias=null;
        if (str_starts_with($path,'/opt/')) {
            $boundary=realpath('/opt');
            if ($boundary===false) throw new RuntimeException('existing_dns_rules');
            $alias='/opt';$canonical=$boundary.substr($path,4);
        }
        $reader=new AsusShareRead($owner,$boundary,$alias);
        $stat=$reader->stat($canonical);
        if (!$stat || $stat['uid']!==$owner || ($stat['mode']&0022)!==0) throw new RuntimeException('existing_dns_rules');
        try {$value=$reader->bytes($canonical,262144);}catch(Throwable $e){throw new RuntimeException('existing_dns_rules');}
        return ['value'=>$value,'fingerprint'=>['sha256'=>hash('sha256',$value),
            'file'=>array_intersect_key($stat,array_flip(['dev','ino','mode','uid','nlink','size','mtime','ctime']))]];
    }
    public static function collect(string $text,int $owner=0): array
    {
        $result=self::walk($text,static fn($path)=>self::read($path,$owner));$fingerprints=[];
        foreach ($result['files'] as $path=>$entry) {
            if (self::read($path,$owner)!==$entry) throw new RuntimeException('existing_dns_rules');
            $fingerprints[$path]=$entry['fingerprint'];
        }
        ksort($fingerprints);
        return ['text'=>$result['text'],'fingerprints'=>$fingerprints];
    }
}
