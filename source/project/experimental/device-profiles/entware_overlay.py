"""Exact private Entware integration; never modifies a router itself."""


def patch_entware(files):
    result=dict(files)
    if set(result)!={'init','lifecycle','platform'}:
        raise ValueError('unsupported_entware_layout')
    if any('NFQWS_DEVICE_PROFILES_EXPERIMENT' in value for value in result.values()):
        raise ValueError('already_patched')

    def replace(key,old,new):
        if result[key].count(old)!=1:
            raise ValueError('unsupported_entware_layout: '+key)
        result[key]=result[key].replace(old,new)

    replace('init','. /opt/lib/nfqws2-asus/lifecycle.sh\n',
            '. /opt/lib/nfqws2-asus/lifecycle.sh\n'
            '# NFQWS_DEVICE_PROFILES_EXPERIMENT\n'
            '. /opt/lib/nfqws2-asus/device-profiles-entware.sh || exit 1\n')
    replace('lifecycle','asus_kill() {\n',
            'asus_kill() {\n'
            '    # NFQWS_DEVICE_PROFILES_EXPERIMENT: all restart paths share ownership checks.\n'
            '    nfqws_lab_entware_stop || return 1\n')
    replace('lifecycle','    asus_detach_family iptables\n',
            '    asus_detach_family iptables || return 1\n')
    replace('lifecycle','\n    command -v ip6tables >/dev/null 2>&1 && asus_detach_family ip6tables\n',
            '\n    if command -v ip6tables >/dev/null 2>&1; then asus_detach_family ip6tables || return 1; fi\n')
    replace('lifecycle','    asus_rules "$family" mangle > "$RUN_DIR/rules$family" || return 1\n',
            '    nfqws_lab_entware_firewall_guard "$family" || return 1\n'
            '    asus_rules "$family" mangle > "$RUN_DIR/rules$family" || return 1\n')
    replace('lifecycle','    asus_attach "$cmd" mangle PREROUTING nfqa_pre || return 1\n',
            '    nfqws_lab_entware_firewall_mark "$family" || return 1\n'
            '    asus_attach "$cmd" mangle PREROUTING nfqa_pre || return 1\n')
    replace('lifecycle','    asus_check || return 1\n',
            '    # A dead main process may have left profile queues behind.\n'
            '    asus_firewall_stop || return 1\n'
            '    nfqws_lab_entware_stop || return 1\n'
            '    asus_check || return 1\n'
            '    ASUS_WAN=$(asus_interfaces) || ASUS_WAN=\'\'\n'
            '    nfqws_lab_entware_preflight || return 1\n')
    replace('lifecycle',"    if ! asus_firewall_apply; then asus_error 'Firewall setup failed'; asus_failed_start; return 1; fi\n",
            '    nfqws_lab_entware_start || { asus_failed_start; return 1; }\n'
            "    if ! asus_firewall_apply; then asus_error 'Firewall setup failed'; asus_failed_start; return 1; fi\n")
    replace('lifecycle','    if asus_snapshot > "$RUN_DIR/current" 2>/dev/null &&\n',
            '    nfqws_lab_entware_reconcile || return 1\n'
            '    if asus_snapshot > "$RUN_DIR/current" 2>/dev/null &&\n')
    replace('lifecycle','    if asus_running && asus_snapshot >/dev/null 2>&1; then\n',
            '    if asus_running && asus_snapshot >/dev/null 2>&1 && nfqws_lab_entware_ready; then\n')
    replace('lifecycle','        for chain in nfqa_pre nfqa_post nfqa_in nfqa_out; do\n',
            '        nfqws_lab_entware_snapshot "$cmd" || return 1\n'
            '        for chain in nfqa_pre nfqa_post nfqa_in nfqa_out; do\n')
    replace('platform','    for dest in out in; do\n',
            '    # NFQWS_DEVICE_PROFILES_EXPERIMENT: exclusions in pre/post already ran.\n'
            '    nfqws_lab_entware_fragment "$family" || return 1\n'
            '    for dest in out in; do\n')
    # Flush base references first, then private profile chains; only then delete.
    replace('platform','        for chain in $clients; do "$cmd" -w -t "$table" -X "$chain" 2>/dev/null; done\n',
            '        if [ "$table" = mangle ]; then nfqws_lab_entware_detach "$cmd" || return 1; fi\n'
            '        for chain in $clients; do "$cmd" -w -t "$table" -X "$chain" 2>/dev/null; done\n')
    return result
