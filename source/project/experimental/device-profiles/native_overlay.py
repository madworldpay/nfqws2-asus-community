"""Generate explicit private hooks for the known native service layout.

This function never touches a router. Deployment compares backed-up file hashes
before atomically replacing each file, then records the resulting hook hashes.
"""


def patch_native(files):
    result=dict(files)
    if set(result)!={'init','control','firewall'}:
        raise ValueError('unsupported_native_layout')
    if any('NFQWS_DEVICE_PROFILES_EXPERIMENT' in text for text in result.values()):
        raise ValueError('already_patched')

    def replace(key,old,new):
        if result[key].count(old)!=1:
            raise ValueError('unsupported_native_layout: '+key)
        result[key]=result[key].replace(old,new)

    replace('init','NFQWS_RUN=${NFQWS_RUN:-/var/run/nfqws2-native}\n',
            'NFQWS_RUN=${NFQWS_RUN:-/var/run/nfqws2-native}\n'
            '# NFQWS_DEVICE_PROFILES_EXPERIMENT\n'
            '. /usr/lib/nfqws2/device-profiles-native.sh || exit 1\n')
    replace('init','    if [ -x /usr/lib/nfqws2/ip-health/service.sh ]; then',
            '    nfqws_lab_instances || return 1\n'
            '    if [ -x /usr/lib/nfqws2/ip-health/service.sh ]; then')
    replace('init','    "$NFQWS_CONTROL" check-started || { stop; return 1; }',
            '    "$NFQWS_CONTROL" check-started || { stop; return 1; }\n'
            '    nfqws_lab_check || { stop; return 1; }')
    replace('control','    file=$(mktemp "$NFQWS_RUN/launch.XXXXXX") || exit 1',
            '    # NFQWS_DEVICE_PROFILES_EXPERIMENT\n'
            '    nfqws_lab_preflight || exit 1\n'
            '    file=$(mktemp "$NFQWS_RUN/launch.XXXXXX") || exit 1')
    replace('firewall','# Native firewall4 integration. Never flush or edit another application\'s table.',
            '# Native firewall4 integration. Never flush or edit another application\'s table.\n'
            '# NFQWS_DEVICE_PROFILES_EXPERIMENT\n'
            '. /usr/lib/nfqws2/device-profiles-native.sh || exit 1')
    replace('firewall','    nfqws_client_set clients4 ipv4_addr "$ASUS_CLIENTS4"',
            '    nfqws_lab_definitions || exit 1\n'
            '    nfqws_client_set clients4 ipv4_addr "$ASUS_CLIENTS4"')
    replace('firewall','        nfqws_client_rules\n',
            '        nfqws_client_rules\n'
            '        nfqws_lab_dispatch "$direction" || exit 1\n')
    # Only the flow-offload capture window uses the union of profile ports.
    # The normal fallback keeps its original capture ports.
    marker='    # Offload only after BOTH capture windows, including a late reply, have passed.'
    replace('firewall',marker,
            '    tcp=$(nfqws_lab_ports "$TCP_PORTS" tcp) || exit 1\n'
            '    udp=$(nfqws_lab_ports "$UDP_PORTS" udp) || exit 1\n'+marker)
    return result


def patch_index(source,dispatcher):
    marker="  if ($_POST['cmd'] === 'dpisitecheck') {"
    update='      session_write_close();$value=AsusUpdateApi::dispatch($_POST);$raw=json_encode($value,JSON_THROW_ON_ERROR);'
    if source.count(marker)!=1 or source.count(update)!=1 or 'deviceprofilesapply' in source:
        raise ValueError('unsupported_dispatcher_layout')
    source=source.replace(marker,dispatcher+'\n'+marker)
    guard='''      // NFQWS_DEVICE_PROFILES_EXPERIMENT_UPDATE
      if(in_array($_POST['cmd'],['packageupdateprepare','packageupdateapply'],true)){
        require_once __DIR__.'/device-profiles-runtime.php';
        if((new NfqwsDeviceProfilesRuntime())->blocksUpdate()){
          http_response_code(409);echo json_encode(['error'=>'experimental_runtime_active']);exit();
        }
      }
'''
    return source.replace(update,guard+update)
