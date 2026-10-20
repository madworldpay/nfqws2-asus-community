<?php
require_once __DIR__.'/smartdns-profile.php';
require_once __DIR__.'/smartdns-install.php';

final class AsusSmartDnsValidationError extends RuntimeException
{
    public function __construct(string $code, public readonly array $checks=[])
    { parent::__construct($code); }
}

/**
 * Configuration coordinator. The trusted candidate adapter must run under an
 * independent guardian, own its children, and always stop them in finally.
 * Nothing from HTTP can supply an executable, command, path or adapter.
 */
final class AsusSmartDnsProbe
{
    public function __construct(private AsusSmartDnsInstaller $installer, private array $deps=[]) {}
    private function now(): float
    {
        $value=isset($this->deps['uptime']) ? ($this->deps['uptime'])() : (float)explode(' ',file_get_contents('/proc/uptime'))[0];
        if(!is_numeric($value) || !is_finite((float)$value) || $value<0)throw new AsusSmartDnsValidationError('invalid_state');
        return (float)$value;
    }
    private function budget(float $end, array $checks): void
    { if($this->now()>=$end)throw new AsusSmartDnsValidationError('timed_out',$checks); }
    private static function ready(mixed $value, string $type): bool
    {
        if(!is_array($value) || ($value['ok']??null)!==true || ($value['rcode']??null)!==0 || ($value['truncated']??null)!==false || !is_array($value['answers']??null) || !array_is_list($value['answers']) || count($value['answers'])<1 || count($value['answers'])>64)return false;
        foreach($value['answers'] as $address) {
            $packed=is_string($address) && strlen($address)<=45 ? @inet_pton($address) : false;
            if($packed===false || strlen($packed)!==($type==='A'?4:16))return false;
        }
        return true;
    }
    private static function emptyAnswer(mixed $value): bool
    {
        // Only the trusted native helper can report a parsed, correlated empty
        // NOERROR reply. Timeout, malformed replies, NXDOMAIN and SERVFAIL fail.
        return is_array($value) && ($value['ok']??null)===false && ($value['rcode']??null)===0
            && ($value['truncated']??null)===false && ($value['answers']??null)===[] && ($value['reason']??null)==='no_address';
    }
    private function candidate(array $profile, array $names, string $stage, ?string $server, string $id, string $hash, string $bundle, float $end, array &$checks): void
    {
        $names=array_values(array_unique($names)); $result=null;
        for($port=16053;$port<=16062;$port++) {
            $this->budget($end,$checks);
            $request=['request_id'=>$id,'profile_hash'=>$hash,'stage'=>$stage,'server_id'=>$server,
                'bundle'=>$bundle,'port'=>$port,'config'=>AsusSmartDnsProfile::render($profile,$port)['config'],
                'names'=>$names,'query_timeout_ms'=>2500,'max_parallel_queries'=>2,'deadline_uptime'=>$end];
            try { $result=($this->deps['candidate'])($request); break; }
            catch(Throwable $e) {
                if($e->getMessage()==='port_busy')continue;
                $code=in_array($e->getMessage(),['timed_out','guard_unavailable','interrupted','output_limit','unsupported_binary','invalid_configuration','insufficient_memory'],true)?$e->getMessage():'dns_validation_failed';
                throw new AsusSmartDnsValidationError($code,$checks);
            }
        }
        if($result===null)throw new AsusSmartDnsValidationError('port_busy',$checks);
        $this->budget($end,$checks);
        if(!is_array($result) || ($result['started']??false)!==true || ($result['syntax_ok']??false)!==true)throw new AsusSmartDnsValidationError('invalid_configuration',$checks);
        $results=$result['results']??null;
        if(!is_array($results) || !array_is_list($results) || count($results)!==count($names)*2)throw new AsusSmartDnsValidationError('dns_validation_failed',$checks);
        $indexed=[];
        foreach($results as $row) {
            if(!is_array($row) || !is_string($row['name']??null) || !in_array($row['name'],$names,true) || !in_array($row['type']??null,['A','AAAA'],true))throw new AsusSmartDnsValidationError('dns_validation_failed',$checks);
            $key=$row['name'].'/'.$row['type'];
            if(isset($indexed[$key]))throw new AsusSmartDnsValidationError('dns_validation_failed',$checks);
            $indexed[$key]=$row;
        }
        foreach($names as $name) {
            $ok=false; $transport=null; $addresses=[]; $empty=0;
            foreach(['A','AAAA'] as $type) {
                $row=$indexed[$name.'/'.$type]??[]; $udp=$row['udp']??null; $tcp=$row['tcp']??null;
                if(self::ready($udp,$type)) { $ok=true; $transport=$transport??'udp'; $addresses=array_merge($addresses,$udp['answers']); }
                elseif(is_array($udp) && ($udp['truncated']??false)===true && self::ready($tcp,$type)) { $ok=true; $transport='tcp'; $addresses=array_merge($addresses,$tcp['answers']); }
                elseif(self::emptyAnswer($udp) || (is_array($udp) && ($udp['truncated']??false)===true && self::emptyAnswer($tcp))) { $empty++; $transport=$transport??'udp'; }
            }
            $noAddress=!$ok && $empty===2;
            $checks[]=['stage'=>$stage,'server_id'=>$server,'name'=>$name,'ok'=>$ok || ($noAddress && $name!=='example.com'),'transport'=>$transport,'answers'=>array_values(array_unique($addresses))]+($noAddress?['code'=>'no_address']:[]);
        }
    }
    public function validate(array $profile, string $requestId): array
    {
        if(!preg_match('/^[a-f0-9]{32}$/D',$requestId))throw new AsusSmartDnsValidationError('invalid_request');
        $profile=AsusSmartDnsProfile::normalize($profile); $hash=AsusSmartDnsProfile::hash($profile);
        if(!isset($this->deps['candidate']) || !is_callable($this->deps['candidate']))throw new AsusSmartDnsValidationError('guard_unavailable');
        if(!isset($this->deps['baseline']) || !is_callable($this->deps['baseline']))throw new AsusSmartDnsValidationError('baseline_unavailable');
        $baseline=($this->deps['baseline'])();
        if(!is_array($baseline) || !is_string($baseline['hash']??null) || !preg_match('/^[a-f0-9]{64}$/D',$baseline['hash']))throw new AsusSmartDnsValidationError('baseline_unavailable');
        $bundle=isset($this->deps['bundle']) ? ($this->deps['bundle'])() : $this->installer->binaryDirectory();
        $checks=[]; $end=$this->now()+90;
        $render=AsusSmartDnsProfile::render($profile,6054);
        // Check the exact selected configuration under the guarded engine.
        // Network answers are observations, never a resolver admission policy:
        // an unavailable optional DNS must not reject or rewrite the profile.
        // Connection/confirmation still verify the actual router DNS path.
        $this->candidate($profile,['example.com'],'profile',null,$requestId,$hash,$bundle,$end,$checks);
        $this->budget($end,$checks);
        return ['schema_version'=>1,'id'=>bin2hex(random_bytes(16)),'profile_hash'=>$hash,'baseline_hash'=>$baseline['hash'],
            'config'=>$render['config'],'groups'=>$render['groups'],'overlaps'=>$render['overlaps'],'checks'=>$checks,
            'expires_uptime'=>$this->now()+600,'scope'=>'configuration_only','service_success_tested'=>false];
    }
}
