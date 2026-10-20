<?php
require_once __DIR__.'/dpi-native.php';
require_once __DIR__.'/dpi-catalog.php';
/** Explicit allowlist projection: native targets, network identities and error text never cross this boundary. */
final class AsusDpiAnalysis
{
    public const METRICS=['ipv4_latency_ms','ipv6_latency_ms','doh_ok','doh_total','dot_ok','dot_total','udp_ok','udp_total','resolvers_total','subst_sub','subst_total','fakeip_sub','ok','total','detected_as','found_as','avg_bps','peak_bps','bytes','drop_at_sec','dc_reachable','dc_total','answered','attempts','gap_ms','timeout_secs','elapsed_ms','kb','received_kb','duration_ms','read_ms','connect_ms','max_concurrent','timeout'];
    public const DETAILS=['none','unclassified','tcp_rst_on_client_hello','dpi_closed_after_client_hello','tcp_rst_on_connect','tls_drop_handshake','timeout_connection','tls_rst_after_client_hello','response_spoofing_wrong_version','response_spoofing_garbage_data','sni_block_unrecognized_name','dpi_alert_handshake_failure','protocol_version_alert','fake_tls_alert','no_root_certificates','cert_expired','self_signed_cert','hostname_mismatch','cert_spoofing','transfer_eof','handshake_eof','server_has_no_tls13','socket_pool_timeout','tls_handshake_timeout','tcp_syn_timeout','syn_timeout','timeout','read_timeout_word','write_timeout_word','domain_not_found','dns_timeout_unavailable','dns_error','tcp_connection_refused','tcp_rst_after_handshake','tcp_connection_reset','connection_aborted','tcp_connection_aborted','net_unreachable','host_unreachable','icmp_admin_prohibited','icmp_time_exceeded','icmp_frag_needed','icmp_parameter_problem','unknown_connection_failure','ipv6_unsupported','quic_server_hello','quic_retry','quic_forged_retry','quic_stateless_reset','quic_version_negotiation','quic_timeout','quic_unreadable_reply','quic_answered_without_handshake','quic_port_unreachable','isp_blockpage','local_ip','redirect_to_host','upgrade_https','http','elapsed','quic_close','alert_close_notify','alert_unexpected_message','alert_bad_record_mac','alert_decryption_failed','alert_record_overflow','alert_decompression_failure','alert_handshake_failure','alert_no_certificate','alert_bad_certificate','alert_unsupported_certificate','alert_certificate_revoked','alert_certificate_expired','alert_certificate_unknown','alert_illegal_parameter','alert_unknown_ca','alert_access_denied','alert_decode_error','alert_decrypt_error','alert_export_restriction','alert_protocol_version','alert_insufficient_security','alert_internal_error','alert_inappropriate_fallback','alert_user_canceled','alert_no_renegotiation','alert_missing_extension','alert_unsupported_extension','alert_certificate_unobtainable','alert_unrecognised_name','alert_bad_certificate_status_response','alert_bad_certificate_hash_value','alert_unknown_psk_identity','alert_certificate_required','alert_no_application_protocol','alert_encrypted_client_hello_required','tls_decrypt_error','tls_invalid_message','tls_inappropriate_message','tls_inappropriate_handshake_message','tls_peer_misbehaved','tls_no_application_protocol'];
    public static function detail(mixed $s): array
    {
        if($s==='')return ['code'=>'none'];if(!is_string($s)||strlen($s)>256)return ['code'=>'unclassified'];
        if(preg_match('/^http_([0-9]{3})$/D',$s,$m))return ['code'=>'http','http_status'=>(int)$m[1]];
        if(preg_match('/^elapsed_([0-9]{1,9})ms$/D',$s,$m))return ['code'=>'elapsed','elapsed_ms'=>(int)$m[1]];
        if(preg_match('/^quic_close_([0-9]{1,9})$/D',$s,$m))return ['code'=>'quic_close','quic_error_code'=>(int)$m[1]];
        if(preg_match('/^(.+)_at_([0-9]{1,6}(?:\.[0-9]{1,3})?)kb$/D',$s,$m)&&in_array($m[1],self::DETAILS,true))return ['code'=>$m[1],'at_kib'=>(float)$m[2]];
        return ['code'=>in_array($s,self::DETAILS,true)?$s:'unclassified'];
    }
    private static function metrics(array $r): array
    {$o=[];foreach(self::METRICS as $k)if(array_key_exists($k,$r)){$v=$r[$k];if($v===null||((is_int($v)||is_float($v))&&is_finite((float)$v)&&$v>=0&&$v<=1e12))$o[$k]=$v;}return $o;}
    private static function status(mixed $v): string
    {return in_array($v,array_merge(AsusDpiCatalog::load()['statuses'],['slow','stalled','blocked','error']),true)?$v:'unknown';}
    private static function row(array $r,string $target): array
    {
        $out=['target'=>$target,'metrics'=>(object)self::metrics($r)];
        if(isset($r['status']))$out['status']=self::status($r['status']);
        if(array_key_exists('detail',$r))$out['detail']=self::detail($r['detail']);
        foreach(['http','tls12','tls13','quic'] as $p)if(isset($r[$p]))$out['values'][$p]=['status'=>self::status($r[$p]),'detail'=>self::detail($r[$p.'_detail']??null)];
        return $out;
    }
    public static function report(array $native): string
    {
        if(($native['type']??null)!=='nfqws2_dpi_native')throw new RuntimeException('invalid_dpi');
        $groups=[];$fingerprints=AsusDpiOptions::metadata()['fingerprints'];
        foreach($native['groups'] as $g){$id=$g['group'];$r=$g['document']['results'][AsusDpiNative::KEYS[$id]];$out=['group'=>$id,'metrics'=>(object)self::metrics($r),'rows'=>[]];
            if($id===0){$out['observations']=['ipv4'=>is_array($r['ipv4']??null),'ipv6'=>is_array($r['ipv6']??null),'tun_observed'=>!empty($r['tun']),'bypass_observed'=>!empty($r['bypass_tools'])];foreach(['ipv4','ipv6'] as $ip)if(isset($r[$ip]['latency_ms']))$out['metrics']->{$ip.'_latency_ms'}=$r[$ip]['latency_ms'];}
            if($id===1)foreach($r['failures']??[] as $i=>$row){$v=self::row($row,'dns-'.($i+1));$v['protocol']=in_array($row['protocol']??null,['udp','doh_wire','dot'],true)?$row['protocol']:'unknown';$out['rows'][]=$v;}
            if($id===2||$id===3)foreach($r as $i=>$row)$out['rows'][]=self::row($row,($id===2?'domain-':'tcp-').($i+1));
            if($id===5)foreach(['download','upload'] as $i=>$key){$row=self::row($r[$key]??[],'transfer-'.($i+1));$row['direction']=$key;$out['rows'][]=$row;}
            if($id===6)foreach($r['domains']??[] as $i=>$d)foreach($d['profiles']??[] as $fp=>$row){$v=self::row($row,'burst-'.($i+1));$v['profile']=in_array($fp,$fingerprints,true)?$fp:'unknown';$v['statuses']=array_map([self::class,'status'],$row['statuses']??[]);$out['rows'][]=$v;}
            $groups[]=$out;
        }
        $o=$native['settings'];$safe=['profile'=>in_array($o['profile']??null,['ru','ir','cn','global'],true)?$o['profile']:'ru','proxy_configured'=>(bool)($o['proxy_configured']??false),'interface_selected'=>!empty($o['interface']),'metrics'=>(object)[]];
        foreach(['MAX_CONCURRENT'=>'max_concurrent','TIMEOUT'=>'timeout'] as $key=>$name)if(isset($o['config'][$key]))$safe['metrics']->$name=$o['config'][$key];
        $coverage=[];foreach(['dns','domains','tcp','sni','burst_domains','quic_unsupported'] as $k)if(isset($native['coverage'][$k]))$coverage[$k]=$native['coverage'][$k];
        $out=['type'=>'nfqws2_dpi','schema_version'=>2,'detector_version'=>AsusDpiOptions::metadata()['version'],'origin'=>'router','started_at'=>$native['started_at'],'finished_at'=>$native['finished_at'],'state'=>$native['state'],'selected_tests'=>$native['selected_tests'],'groups'=>$groups,'coverage'=>(object)$coverage,'context'=>$native['context'],'settings'=>$safe];
        $raw=json_encode($out,JSON_PRETTY_PRINT|JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR)."\n";AsusSupportSchema::validate($raw,'dpi');return $raw;
    }
}
