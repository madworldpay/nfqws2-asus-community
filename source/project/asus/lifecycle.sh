#!/bin/sh
# Runtime implementation, sourced by S51nfqws2.

asus_running() {
    local pid exe binary
    pid=$(cat "$PIDFILE" 2>/dev/null)
    case "$pid" in ''|*[!0-9]*) return 1;; esac
    [ "$pid" -gt 1 ] || return 1
    kill -0 "$pid" 2>/dev/null || return 1
    exe=$(readlink "/proc/$pid/exe" 2>/dev/null)
    binary=$(readlink -f "$NFQWS_BIN" 2>/dev/null) || return 1
    case "$exe" in "$binary"|"$binary (deleted)") return 0;; esac
    return 1
}

asus_lock() {
    [ "${ASUS_LOCK_HELD:-0}" != 1 ] || return 75
    [ ! -L "$RUN_DIR" ] || return 1
    mkdir -p "$RUN_DIR" || return 1
    # The pinned BusyBox stat supports terse output, but not custom formats.
    [ "$(stat -t "$RUN_DIR" | awk '{print $5}')" = 0 ] || return 1
    chmod 700 "$RUN_DIR" || return 1
    [ ! -L "$RUN_DIR/control.lock" ] || return 1
    exec 9>"$RUN_DIR/control.lock" || return 1
    flock -n 9 || return 75
    ASUS_LOCK_HELD=1
    # Kernel releases the lease on exit, including SIGKILL; no stale PID lock.
    # Daemon/scheduler children explicitly close FD 9 below.
    trap 'exit 1' HUP INT TERM
}

asus_firewall_stop() {
    asus_detach_family iptables
    command -v ip6tables >/dev/null 2>&1 && asus_detach_family ip6tables
    rm -f "$RUN_DIR/snapshot"
    return 0
}

asus_attach() {
    local cmd=$1 table=$2 parent=$3 chain=$4
    "$cmd" -w -t "$table" -C "$parent" -j "$chain" >/dev/null 2>&1 ||
        "$cmd" -w -t "$table" -I "$parent" 1 -j "$chain"
}

asus_restore_rules() {
    local cmd=$1
    shift
    if command -v asus_xtables >/dev/null 2>&1; then
        asus_xtables "$cmd" "$@"
    else
        "$cmd" "$@"
    fi
}

asus_firewall_family() {
    local family=$1 cmd=iptables restore=iptables-restore
    case "$family" in
        4) ;;
        6) cmd=ip6tables; restore=ip6tables-restore ;;
        *) return 1 ;;
    esac
    asus_rules "$family" mangle > "$RUN_DIR/rules$family" || return 1
    asus_restore_rules "$restore" --noflush < "$RUN_DIR/rules$family" || return 1
    asus_attach "$cmd" mangle PREROUTING nfqa_pre || return 1
    asus_attach "$cmd" mangle POSTROUTING nfqa_post || return 1
    if [ "$family" = 4 ]; then
        asus_rules 4 nat > "$RUN_DIR/rules-nat" || return 1
        asus_restore_rules "$restore" --noflush < "$RUN_DIR/rules-nat" || return 1
        asus_attach "$cmd" nat POSTROUTING nfqa_nat || return 1
    fi
}

asus_snapshot() {
    local cmd chain family
    for family in 4 6; do
        [ "$family" = 6 ] && [ "$IPV6_ENABLED" != 1 ] && continue
        [ "$family" = 4 ] && cmd=iptables || cmd=ip6tables
        "$cmd" -w -t mangle -C PREROUTING -j nfqa_pre >/dev/null 2>&1 || return 1
        "$cmd" -w -t mangle -C POSTROUTING -j nfqa_post >/dev/null 2>&1 || return 1
        for chain in nfqa_pre nfqa_post nfqa_in nfqa_out; do
            "$cmd" -w -t mangle -S "$chain" || return 1
        done
    done
    iptables -w -t nat -C POSTROUTING -j nfqa_nat >/dev/null 2>&1 || return 1
    iptables -w -t nat -S nfqa_nat
}

asus_firewall_apply() {
    if ! asus_firewall_family 4; then asus_firewall_stop; return 1; fi
    if [ "$IPV6_ENABLED" = 1 ]; then
        if ! asus_firewall_family 6; then asus_firewall_stop; return 1; fi
    else
        command -v ip6tables >/dev/null 2>&1 && asus_detach_family ip6tables
    fi
    asus_snapshot > "$RUN_DIR/snapshot.new" || { asus_firewall_stop; return 1; }
    mv "$RUN_DIR/snapshot.new" "$RUN_DIR/snapshot"
    printf '%s\n' "$ASUS_WAN" > "$RUN_DIR/wan"
}

asus_sysctls() {
    local key desired old
    [ -e "$RUN_DIR/sysctls" ] || : > "$RUN_DIR/sysctls"
    for key in nf_conntrack_acct nf_conntrack_checksum nf_conntrack_tcp_be_liberal; do
        desired=1; [ "$key" = nf_conntrack_checksum ] && desired=0
        key="net.netfilter.$key"
        old=$(sysctl -n "$key" 2>/dev/null) || return 1
        if [ "$old" != "$desired" ]; then
            # Retain the original value across reconcile retries.
            grep -q "^$key " "$RUN_DIR/sysctls" || printf '%s %s %s\n' "$key" "$old" "$desired" >> "$RUN_DIR/sysctls"
            sysctl -w "$key=$desired" >/dev/null || return 1
        fi
    done
}

asus_restore_sysctls() {
    local key old applied now
    if [ -f "$RUN_DIR/sysctls" ]; then
        while read -r key old applied; do
            now=$(sysctl -n "$key" 2>/dev/null)
            [ "$now" != "$applied" ] || sysctl -w "$key=$old" >/dev/null
        done < "$RUN_DIR/sysctls"
        rm -f "$RUN_DIR/sysctls"
    fi
    return 0
}

asus_check() {
    local cmd
    [ "$(id -u)" = 0 ] || { asus_error 'Run as the router administrator (UID 0).'; return 1; }
    asus_model || return 1
    [ "$(nvram get sw_mode 2>/dev/null)" = 1 ] || {
        asus_error 'ASUS must operate in router mode (sw_mode=1). AP/bridge mode is not supported.'; return 1;
    }
    . /opt/lib/nfqws2-asus/target.sh || return 1
    # postinst still holds opkg's lock; never re-enter the package manager here.
    . /opt/lib/nfqws2-asus/abi.sh || return 1
    asus_resolve_package_abi "$ASUS_PACKAGE_ARCH" >/dev/null || {
        asus_error "Unsupported Entware ABI for $ASUS_PACKAGE_ARCH."; return 1;
    }
    /opt/libexec/nfqws2-asus/busybox true || {
        asus_error 'The private runtime cannot execute on this firmware.'; return 1;
    }
    for cmd in nvram cru ip iptables iptables-restore sysctl; do
        command -v "$cmd" >/dev/null 2>&1 || { asus_error "Missing command: $cmd"; return 1; }
    done
    [ -x "$NFQWS_BIN" ] || { asus_error 'nfqws2 binary missing'; return 1; }
    asus_validate || return 1
    asus_load_modules
    asus_choose_tools || {
        asus_error 'Netfilter tools or local conntrack direction check failed. Inspect firmware support; IPv6 processing needs its own working matches.'; return 1;
    }
    if command -v asus_diagnostics_json >/dev/null 2>&1; then
        local diagnostics
        diagnostics=$(asus_diagnostics_json "$NFQUEUE_NUM")
        case "$diagnostics" in *'"loaded":"loaded"'*)
            asus_error 'WARNING: ARK is loaded; NFQUEUE delivery may conflict. Inspect ASUS preparation in the web panel.';;
        esac
    fi
    printf 'Kernel preflight passed. Traffic/offload compatibility still needs a router test.\n'
}

asus_kill() {
    local tries=0 pid
    if asus_running; then
        pid=$(cat "$PIDFILE")
        kill -TERM "$pid" || return 1
        while asus_running && [ "$tries" -lt 5 ]; do sleep 1; tries=$((tries + 1)); done
        # Do not SIGKILL an unresponsive daemon or remove its live PID file.
        asus_running && { asus_error 'Daemon did not stop; inspect it before restarting.'; return 1; }
    fi
    rm -f "$PIDFILE"
}

asus_stop() {
    cru d nfqws2_asus 8>&- 9>&- >/dev/null 2>&1
    rm -f "$RUN_DIR/enabled" "$RUN_DIR/started" "$RUN_DIR/watchdog-state"
    asus_firewall_stop
    asus_kill || return 1
    asus_restore_sysctls
    rm -f "$RUN_DIR/runtime.conf" "$RUN_DIR/wan"
    echo 'Stopped NFQWS2 ASUS service'
}

asus_failed_start() {
    if [ "${ASUS_RECONCILING:-0}" = 1 ]; then
        # Preserve the requested running state and config for the next retry.
        asus_firewall_stop
        asus_kill || return 1
        asus_restore_sysctls
    else
        asus_stop
    fi
    return 1
}

asus_start() {
    local tries=0
    if asus_running; then
        if [ "${ASUS_RECONCILING:-0}" != 1 ]; then
            rm -f "$RUN_DIR/watchdog-state"
            command -v nfqws_watchdog_running >/dev/null 2>&1 && nfqws_watchdog_running
        fi
        echo 'Service NFQWS2 is already running'; return 0
    fi
    asus_check || return 1
    # Runtime settings are an explicit snapshot; saving the form does not
    # silently apply only the firewall half of a new configuration.
    if [ "${ASUS_RECONCILING:-0}" != 1 ] || [ ! -f "$RUN_DIR/runtime.conf" ]; then
        cp "$CONFFILE" "$RUN_DIR/runtime.conf" || return 1
    fi
    if command -v asus_save_compatibility >/dev/null 2>&1; then
        asus_save_compatibility || return 1
    fi
    if [ "${ASUS_RECONCILING:-0}" != 1 ]; then
        # An explicit start rearms recovery even when it must wait for WAN.
        rm -f "$RUN_DIR/started" "$RUN_DIR/watchdog-state"
    fi
    cru a nfqws2_asus '* * * * * /opt/etc/init.d/S51nfqws2 reconcile >/dev/null 2>&1' 8>&- 9>&- || return 1
    touch "$RUN_DIR/enabled"
    ASUS_WAN=$(asus_interfaces)
    if [ -z "$ASUS_WAN" ]; then
        asus_firewall_stop
        echo 'Waiting for WAN. The ASUS scheduler will retry within one minute.'
        return 0
    fi
    if ! asus_sysctls; then asus_failed_start; return 1; fi
    # Only a genuine WAN wait is free to reconcile without the watchdog.
    # A daemon launch was attempted even if it exits before readiness succeeds.
    touch "$RUN_DIR/started" || return 1
    # Same argument construction as the pinned upstream package; no eval.
    if ! "$NFQWS_BIN" --daemon --pidfile="$PIDFILE" $(ISP_INTERFACE="$ASUS_WAN"; _startup_args) 7>&- 8>&- 9>&-; then
        asus_failed_start; return 1
    fi
    while ! asus_running && [ "$tries" -lt 3 ]; do sleep 1; tries=$((tries + 1)); done
    if ! asus_running; then asus_error 'Daemon failed to start'; asus_failed_start; return 1; fi
    if ! asus_firewall_apply; then asus_error 'Firewall setup failed'; asus_failed_start; return 1; fi
    if [ "${ASUS_RECONCILING:-0}" != 1 ]; then rm -f "$RUN_DIR/watchdog-state"; fi
    command -v nfqws_watchdog_running >/dev/null 2>&1 && nfqws_watchdog_running
    echo 'Started NFQWS2 ASUS service. Verify nfqa_in/nfqa_out packet counters.'
}

asus_scheduler_lock() {
    # Core/update leases are already held by S51. Import writers use this same
    # inode; nonblocking acquisition avoids inversion with their core action.
    local directory=/opt/var/lib/nfqws2-asus/import
    [ ! -L "$directory" ] || return 2
    (umask 077; mkdir -p "$directory") || return 2
    [ "$(stat -t "$directory" | awk '{print $5}')" = 0 ] || return 2
    [ "$(stat -t "$directory" | awk '{print $4}')" = 41c0 ] || return 2
    [ ! -L "$directory/writer.lock" ] || return 2
    if [ -e "$directory/writer.lock" ]; then nfqws_restart_state_safe "$directory/writer.lock" || return 2; fi
    exec 7>>"$directory/writer.lock" || return 2
    flock -n 7 || return 1
}

asus_watchdog_recover() (
    command -v nfqws_watchdog_due >/dev/null 2>&1 || return 0
    nfqws_restart_settings && [ "$NFQWS_WATCHDOG_ENABLED" = 1 ] || return 0
    asus_scheduler_lock || return 0
    nfqws_watchdog_attempt || return 0
    asus_start
)

asus_restart_scheduled() (
    local pid
    command -v nfqws_restart_schedule_due >/dev/null 2>&1 || return 1
    pid=$(cat "$PIDFILE" 2>/dev/null)
    nfqws_restart_schedule_due "$pid" || return 1
    asus_scheduler_lock || return 1
    # A save could have changed the revision while the writer lease was busy.
    nfqws_restart_schedule_due "$pid" || return 1
    asus_validate && asus_firewall_stop && asus_kill && asus_start || return 2
)

asus_reconcile() {
    [ -f "$RUN_DIR/enabled" ] || return 0
    ASUS_RECONCILING=1
    if ! asus_running; then
        # No prior daemon means the explicit start is still waiting for WAN.
        if [ ! -f "$RUN_DIR/started" ]; then asus_start; else asus_watchdog_recover; fi
        return $?
    fi
    command -v nfqws_watchdog_running >/dev/null 2>&1 && nfqws_watchdog_running
    local scheduled
    asus_restart_scheduled; scheduled=$?
    case "$scheduled" in 0) return 0;; 1) ;; *) return 1;; esac
    ASUS_WAN=$(asus_interfaces)
    if [ -z "$ASUS_WAN" ]; then asus_firewall_stop; return 0; fi
    if [ "$(cat "$RUN_DIR/wan" 2>/dev/null)" != "$ASUS_WAN" ]; then
        # Socket binding / multi-WAN arguments must follow the new interface set.
        asus_firewall_stop
        # A deliberate network rebind keeps its existing WAN retry behavior;
        # it is not counted as an unexpected process exit by the watchdog.
        rm -f "$RUN_DIR/started"
        asus_kill && asus_start
        return $?
    fi
    if asus_snapshot > "$RUN_DIR/current" 2>/dev/null &&
        cmp -s "$RUN_DIR/current" "$RUN_DIR/snapshot"; then return 0; fi
    asus_firewall_apply
}

asus_status() {
    if asus_running && asus_snapshot >/dev/null 2>&1; then
        echo 'Service NFQWS2 is running'
        echo 'Daemon and firewall ready; verify packet counters to confirm processing.'
    elif [ -f "$RUN_DIR/enabled" ]; then
        echo 'Service NFQWS2 is waiting for WAN or firewall recovery'
        return 1
    else
        echo 'Service NFQWS2 is stopped'
        return 1
    fi
}
