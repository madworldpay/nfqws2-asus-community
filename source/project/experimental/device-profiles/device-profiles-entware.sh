#!/opt/libexec/nfqws2-asus/busybox sh
# NFQWS_DEVICE_PROFILES_EXPERIMENT: private ASUS/Entware service integration.
# Sourced by S51nfqws2; this is never a separate boot service.

nfqws_lab_entware_php() {
    /opt/bin/php-cgi -n -d register_argc_argv=1 -d max_execution_time=0 \
        -d memory_limit=48M -q -f /opt/share/nfqws-asus-web/device-profiles-runtime.php -- "$@"
}
nfqws_lab_entware_active() {
    printf '%s\n' "${NFQWS_LAB_RUN:-${RUN_DIR:-/tmp/nfqws2-asus}/device-profiles/active}"
}
nfqws_lab_entware_root() {
    printf '%s/device-profiles\n' "${RUN_DIR:-/tmp/nfqws2-asus}"
}
nfqws_lab_entware_hash() {
    sha256sum "$1" | awk '{print $1}'
}
nfqws_lab_entware_private() {
    local dir=$1 owner mode
    [ ! -L "$dir" ] && [ -d "$dir" ] || return 1
    owner=$(stat -t "$dir" | awk '{print $5}')
    mode=$(stat -t "$dir" | awk '{print $4}')
    [ "$owner" = 0 ] && [ "$mode" = 41c0 ]
}
nfqws_lab_entware_file() {
    local path=$1 facts
    [ ! -L "$path" ] && [ -f "$path" ] || return 1
    facts=$(stat -t "$path") || return 1
    # BusyBox stat terse: name size blocks mode uid gid dev inode links ...
    [ "$(printf '%s\n' "$facts" | awk '{print $5}')" = 0 ] || return 1
    [ "$(printf '%s\n' "$facts" | awk '{print $9}')" = 1 ] || return 1
    [ "$(printf '%s\n' "$facts" | awk '{print $4}')" = 8180 ]
}
nfqws_lab_entware_fragment() {
    local family=$1 file
    case "$family" in 4|6) ;; *) return 1;; esac
    file=$(nfqws_lab_entware_active)/rules-entware$family.restore
    [ -e "$file" ] || return 0
    nfqws_lab_entware_file "$file" || return 1
    cat "$file"
}
nfqws_lab_entware_fragment_chains() {
    local file=$1
    [ -e "$file" ] || return 0
    nfqws_lab_entware_file "$file" || return 1
    sed -n 's/^:\(nfqa_dp_[0-9][0-9]*_\(in\|out\)\) .*/\1/p' "$file"
}
nfqws_lab_entware_firewall_guard() {
    local family=$1 cmd=iptables root file manifest chain expected actual chains
    case "$family" in 4) ;; 6) cmd=ip6tables;; *) return 1;; esac
    root=$(nfqws_lab_entware_root);file=$(nfqws_lab_entware_active)/rules-entware$family.restore
    manifest=$root/firewall$family.snapshot
    chains=$(nfqws_lab_entware_fragment_chains "$file") || return 1
    if [ -e "$manifest" ]; then
        nfqws_lab_entware_private "$root" && nfqws_lab_entware_file "$manifest" || return 1
        chains="$chains $(sed -n 's/^-N \(nfqa_dp_[0-9][0-9]*_\(in\|out\)\)$/\1/p' "$manifest")"
    fi
    for chain in $chains; do
        actual=$("$cmd" -w -t mangle -S "$chain" 2>/dev/null) || continue
        [ -f "$manifest" ] || return 1
        expected=$(awk -v chain="$chain" '$2==chain' "$manifest")
        [ -n "$expected" ] && [ "$actual" = "$expected" ] || return 1
    done
}
nfqws_lab_entware_firewall_mark() {
    local family=$1 cmd=iptables root file manifest chain
    case "$family" in 4) ;; 6) cmd=ip6tables;; *) return 1;; esac
    root=$(nfqws_lab_entware_root);file=$(nfqws_lab_entware_active)/rules-entware$family.restore
    [ ! -L "$root" ] || return 1
    (umask 077; mkdir -p "$root") || return 1
    nfqws_lab_entware_private "$root" || return 1
    manifest=$root/firewall$family.snapshot
    [ ! -e "$manifest" ] || nfqws_lab_entware_file "$manifest" || return 1
    [ ! -L "$manifest.new" ] || return 1
    (umask 077
        for chain in $(nfqws_lab_entware_fragment_chains "$file"); do
            "$cmd" -w -t mangle -S "$chain" || exit 1
        done > "$manifest.new"
    ) || return 1
    mv "$manifest.new" "$manifest"
}
nfqws_lab_entware_snapshot() {
    local cmd=$1 chain family=4 file
    [ "$cmd" != ip6tables ] || family=6
    file=$(nfqws_lab_entware_active)/rules-entware$family.restore
    [ -e "$file" ] || return 0
    nfqws_lab_entware_file "$file" || return 1
    for chain in $(sed -n 's/^:\(nfqa_dp_[0-9][0-9]*_\(in\|out\)\) .*/\1/p' "$file"); do
        "$cmd" -w -t mangle -S "$chain" || return 1
    done
}
nfqws_lab_entware_detach() {
    local cmd=$1 chain family manifest
    case "$cmd" in iptables) family=4;; ip6tables) family=6;; *) return 1;; esac
    manifest=$(nfqws_lab_entware_root)/firewall$family.snapshot
    [ -e "$manifest" ] || return 0
    nfqws_lab_entware_firewall_guard "$family" || return 1
    for chain in $(sed -n 's/^-N \(nfqa_dp_[0-9][0-9]*_\(in\|out\)\)$/\1/p' "$manifest"); do
        "$cmd" -w -t mangle -S "$chain" >/dev/null 2>&1 || continue
        "$cmd" -w -t mangle -F "$chain" || return 1
        "$cmd" -w -t mangle -X "$chain" || return 1
    done
    rm -f "$manifest"
}
nfqws_lab_entware_validate_fragment() (
    # Old firmware lacks iptables-restore --test. Round-trip a detached candidate
    # using the already-probed matching CLI/restore pair; no live base chain exists here.
    local family=$1 cmd=iptables file dir prefix chain acct
    case "$family" in 4) ;; 6) cmd=ip6tables;; *) exit 1;; esac
    dir=$(nfqws_lab_entware_active);file=$dir/rules-entware$family.restore
    [ -e "$file" ] || exit 0
    nfqws_lab_entware_file "$file" || exit 1
    acct=$(sysctl -n net.netfilter.nf_conntrack_acct 2>/dev/null) || exit 1
    case "$acct" in 0|1) ;; *) exit 1;; esac
    prefix=nfqa_dpt_$$_
    # Refuse collision before restore could flush an existing chain.
    for chain in "${prefix}in" "${prefix}out" $(sed -n 's/^:\(nfqa_dp_[0-9][0-9]*_\(in\|out\)\) .*/\1/p' "$file" | sed "s/^nfqa_dp_/$prefix/"); do
        "$cmd" -w -t mangle -S "$chain" >/dev/null 2>&1 && exit 1
    done
    trap 'for chain in "${prefix}in" "${prefix}out" $(sed -n "s/^:\\(${prefix}[0-9][0-9]*_\\(in\\|out\\)\\) .*/\\1/p" "$dir/probe-$$.restore" 2>/dev/null); do
        "$cmd" -w -t mangle -F "$chain" >/dev/null 2>&1; done
        for chain in "${prefix}in" "${prefix}out" $(sed -n "s/^:\\(${prefix}[0-9][0-9]*_\\(in\\|out\\)\\) .*/\\1/p" "$dir/probe-$$.restore" 2>/dev/null); do
        "$cmd" -w -t mangle -X "$chain" >/dev/null 2>&1; done
        rm -f "$dir/probe-$$.restore"
        if [ "$acct" = 0 ] && [ "$(sysctl -n net.netfilter.nf_conntrack_acct 2>/dev/null)" = 1 ]; then
            sysctl -w net.netfilter.nf_conntrack_acct=0 >/dev/null; fi' EXIT
    umask 077
    {
        printf '*mangle\n:%sin - [0:0]\n:%sout - [0:0]\n' "$prefix" "$prefix"
        awk -v prefix="$prefix" '{for(i=1;i<=NF;i++) {
            colon=substr($i,1,1)==":"; value=colon?substr($i,2):$i;
            if(value=="nfqa_in")value=prefix "in";
            else if(value=="nfqa_out")value=prefix "out";
            else if(value ~ /^nfqa_dp_[0-9]+_(in|out)$/)sub(/^nfqa_dp_/,prefix,value);
            $i=(colon?":":"")value;
        } print}' "$file"
        printf 'COMMIT\n'
    } > "$dir/probe-$$.restore" || exit 1
    asus_restore_rules "$cmd-restore" --noflush < "$dir/probe-$$.restore"
)
nfqws_lab_entware_preflight() {
    nfqws_lab_entware_php preflight "${ASUS_WAN:-}" || return 1
    nfqws_lab_entware_validate_fragment 4 || return 1
    [ "${IPV6_ENABLED:-0}" != 1 ] || nfqws_lab_entware_validate_fragment 6
}
nfqws_lab_entware_ticks() {
    # comm may contain spaces and parentheses. starttime is field 20 after comm.
    sed 's/^.*) //' "/proc/$1/stat" 2>/dev/null | awk '$1 != "Z" {print $20}'
}
nfqws_lab_entware_identity() {
    local slot=$1 root path
    root=$(nfqws_lab_entware_root);path=$root/engine-$slot.identity
    nfqws_lab_entware_private "$root" && nfqws_lab_entware_file "$path" || return 1
    awk -v q="$((41000 + slot))" '
        NR==1 {if($0 !~ /^[0-9]+$/ || $0+0<2)exit 1}
        NR==2 {if($0 !~ /^[0-9]+$/)exit 1}
        NR==3 {if($0 !~ /^[a-f0-9-]+$/ || length($0)!=36)exit 1}
        NR==4 {if($0!=q)exit 1}
        NR==5 {if($0 !~ /^[a-f0-9]+$/ || length($0)!=64)exit 1}
        NR>5 {exit 1}
        END {if(NR!=5)exit 1}' "$path" || return 1
    cat "$path"
}
nfqws_lab_entware_owned() {
    local slot=$1 root pid ticks boot queue hash extra exe expected actual
    root=$(nfqws_lab_entware_root)
    nfqws_lab_entware_identity "$slot" >/dev/null || return 1
    {
        read -r pid;read -r ticks;read -r boot;read -r queue;read -r hash;read -r extra
    } < "$root/engine-$slot.identity"
    [ -z "$extra" ] || return 1
    case "$pid:$ticks:$queue:$hash" in *[!0-9a-f:]*|'') return 1;; esac
    [ "$pid" -gt 1 ] && [ "$queue" = "$((41000 + slot))" ] || return 1
    nfqws_lab_entware_file "$root/engine-$slot.pid" || return 1
    [ "$(cat "$root/engine-$slot.pid" 2>/dev/null)" = "$pid" ] || return 1
    [ "$(cat /proc/sys/kernel/random/boot_id 2>/dev/null)" = "$boot" ] || return 1
    [ "$(nfqws_lab_entware_ticks "$pid")" = "$ticks" ] || return 1
    exe=$(readlink "/proc/$pid/exe" 2>/dev/null) || return 1
    expected=$(readlink -f "${NFQWS_BIN:-/opt/usr/bin/nfqws2}") || return 1
    case "$exe" in "$expected"|"$expected (deleted)") ;; *) return 1;; esac
    actual=$(nfqws_lab_entware_hash "/proc/$pid/cmdline") || return 1
    [ "$actual" = "$hash" ] || return 1
    printf '%s\n' "$pid"
}
nfqws_lab_entware_start() {
    local root active slot args pid tries ticks hash expected
    root=$(nfqws_lab_entware_root);active=$(nfqws_lab_entware_active)
    [ ! -L "$root" ] || return 1
    (umask 077; mkdir -p "$root") || return 1
    nfqws_lab_entware_private "$root" || return 1
    for slot in 0 1 2 3; do
        [ -e "$active/args.$slot" ] || continue
        nfqws_lab_entware_file "$active/args.$slot" || return 1
        [ ! -e "$root/engine-$slot.identity" ] && [ ! -L "$root/engine-$slot.identity" ] &&
            [ ! -e "$root/engine-$slot.pid" ] && [ ! -L "$root/engine-$slot.pid" ] || return 1
        args=$(cat "$active/args.$slot") || return 1
        [ -n "$args" ] && [ "${#args}" -le 131072 ] || return 1
        set -f;set -- $args
        [ "$1" = --user=nobody ] && [ "$2" = "--qnum=$((41000 + slot))" ] || return 1
        expected=$(printf '%s\0' "$NFQWS_BIN" --daemon "--pidfile=$root/engine-$slot.pid" "$@" | sha256sum | awk '{print $1}')
        "$NFQWS_BIN" --daemon "--pidfile=$root/engine-$slot.pid" "$@" 7>&- 8>&- 9>&- || return 1
        tries=0;pid=''
        while [ "$tries" -lt 20 ]; do
            pid=$(cat "$root/engine-$slot.pid" 2>/dev/null)
            case "$pid" in ''|*[!0-9]*) ;; *) [ -r "/proc/$pid/cmdline" ] && break;; esac
            sleep 0.1;tries=$((tries + 1))
        done
        case "$pid" in ''|*[!0-9]*) return 1;; esac
        ticks=$(nfqws_lab_entware_ticks "$pid");case "$ticks" in ''|*[!0-9]*) return 1;; esac
        hash=$(nfqws_lab_entware_hash "/proc/$pid/cmdline") || return 1
        [ "$hash" = "$expected" ] || return 1
        (umask 077; printf '%s\n' "$pid" "$ticks" "$(cat /proc/sys/kernel/random/boot_id)" "$((41000 + slot))" "$hash" > "$root/engine-$slot.identity") || return 1
        nfqws_lab_entware_owned "$slot" >/dev/null || return 1
    done
    nfqws_lab_entware_ready
}
nfqws_lab_entware_stop() {
    local root slot pid tries
    root=$(nfqws_lab_entware_root)
    [ -e "$root" ] || return 0
    nfqws_lab_entware_private "$root" || return 1
    for slot in 0 1 2 3; do
        if [ ! -e "$root/engine-$slot.identity" ]; then
            # An unproven PID is never permission to signal or erase a live task.
            [ ! -e "$root/engine-$slot.pid" ] || return 1
            continue
        fi
        if ! pid=$(nfqws_lab_entware_owned "$slot"); then
            nfqws_lab_entware_identity "$slot" >/dev/null || return 1
            pid=$(sed -n '1p' "$root/engine-$slot.identity")
            # A dead/zombie daemon cannot hold its NFQUEUE. A live mismatched
            # process may have reused the PID and is deliberately left alone.
            [ -z "$(nfqws_lab_entware_ticks "$pid")" ] || return 1
            rm -f "$root/engine-$slot.identity" "$root/engine-$slot.pid" || return 1
            continue
        fi
        kill -TERM "$pid" || return 1
        tries=0
        while nfqws_lab_entware_owned "$slot" >/dev/null && [ "$tries" -lt 50 ]; do
            sleep 0.1;tries=$((tries + 1))
        done
        nfqws_lab_entware_owned "$slot" >/dev/null && return 1
        # A changed identity is not a successful shutdown. Only absent/zombie
        # original processes may release their private metadata.
        [ -z "$(nfqws_lab_entware_ticks "$pid")" ] || return 1
        rm -f "$root/engine-$slot.identity" "$root/engine-$slot.pid" || return 1
    done
}
nfqws_lab_entware_ready() { nfqws_lab_entware_php check >/dev/null 2>&1; }
nfqws_lab_entware_reconcile() {
    local before after active
    active=$(nfqws_lab_entware_active)
    before=$(sha256sum "$active/rules-entware4.restore" "$active/rules-entware6.restore" 2>/dev/null)
    nfqws_lab_entware_php reconcile || return 1
    after=$(sha256sum "$active/rules-entware4.restore" "$active/rules-entware6.restore" 2>/dev/null)
    [ "$before" = "$after" ] || asus_firewall_apply
}

nfqws_lab_entware_main() {
    PATH=/opt/lib/nfqws2-asus/bin:/opt/sbin:/opt/bin:/opt/usr/sbin:/opt/usr/bin:/usr/sbin:/usr/bin:/sbin:/bin
    export PATH
    [ "$(id -u)" = 0 ] || return 2
    local action=$1 id=${2:-}
    case "$action" in
        work|guard|validate)
            [ "$#" = 2 ] && [ "${#id}" = 32 ] || return 2
            case "$id" in *[!0-9a-f]*) return 2;; esac;;
        reconcile) [ "$#" = 1 ] || return 2;;
        *) return 2;;
    esac
    PATH=/opt/lib/nfqws2-asus/bin:/opt/sbin:/opt/bin:/opt/usr/sbin:/opt/usr/bin:/usr/sbin:/usr/bin:/sbin:/bin
    export PATH
    umask 077;set -f
    unset REQUEST_METHOD QUERY_STRING CONTENT_TYPE CONTENT_LENGTH SCRIPT_FILENAME
    RUN_DIR=/tmp/nfqws2-asus;PIDFILE=$RUN_DIR/pid
    NFQWS_BIN=/opt/usr/bin/nfqws2;CONFFILE=/opt/etc/nfqws2/nfqws2.conf
    . /opt/lib/nfqws2-asus/update/lifecycle.sh || return 1
    if ! asus_update_enter core restart; then
        case "$action" in work|guard) nfqws_lab_entware_php queued-failure "$id";; esac
        return 1
    fi
    case "$action" in
        work|guard) nfqws_lab_entware_php "$action" "$id";;
        validate)
            . /opt/lib/nfqws2-asus/platform.sh || return 1
            . /opt/lib/nfqws2-asus/lifecycle.sh || return 1
            . /opt/lib/nfqws2-asus/compatibility.sh || return 1
            . /opt/lib/nfqws2-asus/legacy.sh || return 1
            ASUS_CLIENT_MODE=all;ASUS_CLIENTS4='';ASUS_CLIENTS6='';IPV6_ENABLED=0
            NFQUEUE_NUM=300;USER=nobody;LOG_LEVEL=0
            sh -n "$CONFFILE" && . "$CONFFILE" || return 1
            asus_check || return 1
            ASUS_WAN=$(asus_interfaces) || ASUS_WAN=''
            nfqws_lab_entware_php pending "$id" "$ASUS_WAN" || return 1
            NFQWS_LAB_RUN=$RUN_DIR/device-profiles/pending-$id
            nfqws_lab_entware_validate_fragment 4 || return 1
            [ "$IPV6_ENABLED" != 1 ] || nfqws_lab_entware_validate_fragment 6;;
        reconcile)
            # Ordinary init provides the same update/control leases and config.
            /opt/etc/init.d/S51nfqws2 reconcile 8>&- 9>&-;;
    esac
}
if [ "$0" = /opt/lib/nfqws2-asus/device-profiles-entware.sh ]; then
    nfqws_lab_entware_main "$@"
    exit $?
fi
