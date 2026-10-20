#!/bin/sh
# Private process proof authorizes the worker, never an inherited FD or env flag.
asus_update_transaction() {
    /opt/bin/php-cgi -n -d register_argc_argv=1 -q -f /opt/lib/nfqws2-asus/update/worker.php -- shell-authorize "$1" >/dev/null 2>&1
}

asus_update_enter() {
    local component=$1 action=$2
    case "$component:$action" in
        core:start|core:stop|core:restart|core:reconcile|core:check|web:start|web:stop|web:restart|web:reconcile) ;;
        *) return 2 ;;
    esac
    if asus_update_transaction "$component-$action"; then return 0; fi
    /opt/bin/php-cgi -n -d register_argc_argv=1 -q -f /opt/lib/nfqws2-asus/update/worker.php -- shell-init >/dev/null 2>&1 || return 1
    exec 8>>/opt/var/lib/nfqws2-asus/updates/apply.lock || return 1
    if ! /opt/bin/flock -s -n 8; then
        exec 8>&-
        echo 'An NFQWS2 package update is in progress.' >&2
        return 1
    fi
    if ! /opt/bin/php-cgi -n -d register_argc_argv=1 -q -f /opt/lib/nfqws2-asus/update/worker.php -- shell-check >/dev/null 2>&1; then
        exec 8>&-
        return 1
    fi
    # Held until this init script exits; all long-lived children must close FD8.
}
