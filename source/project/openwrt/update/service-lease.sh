#!/bin/sh
# The actual process proof is checked in PHP; environment/FDs never authorize.
nfqws_native_update_enter() {
    local component=$1 action=$2 permission validation
    case "$component:$action" in
        core:start|core:restart|core:reload|core:boot|core:preflight|core:firewall) permission=core-start;;
        core:stop|core:shutdown|core:remove-firewall) permission=core-stop;;
        web:start|web:restart|web:reload|web:boot) permission=web-start;;
        web:stop|web:shutdown) permission=web-stop;;
        *) return 2;;
    esac
    validation=$permission
    [ "$component:$action" != core:preflight ] || validation=read
    if /usr/bin/php8-cgi -d register_argc_argv=1 -q -f /usr/lib/nfqws2/update/service-guard.php -- authorize "$permission" >/dev/null 2>&1; then return 0; fi
    /usr/bin/php8-cgi -d register_argc_argv=1 -q -f /usr/lib/nfqws2/update/service-guard.php -- init >/dev/null 2>&1 || return 1
    exec 8>>/tmp/nfqws2-native-state/updates/apply.lock || return 1
    if ! /usr/bin/flock -s -n 8; then
        exec 8>&-
        echo 'An NFQWS2 package operation is in progress.' >&2
        return 1
    fi
    if ! /usr/bin/php8-cgi -d register_argc_argv=1 -q -f /usr/lib/nfqws2/update/service-guard.php -- check "$validation" >/dev/null 2>&1; then
        exec 8>&-
        return 1
    fi
    # Native init hands commands to procd; the daemon is not its exec child.
    # Keep FD8 in this caller until the entire ordinary operation returns.
}
