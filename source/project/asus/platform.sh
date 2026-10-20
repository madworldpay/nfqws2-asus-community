#!/bin/sh
# ASUS-specific boundaries. Never sourced on the AI-board OS.

asus_error() { printf 'ASUS NFQWS2: %s\n' "$*" >&2; return 1; }

asus_model() {
    local key model other=''
    for key in productid odmpid; do
        model=$(nvram get "$key" 2>/dev/null)
        [ -z "$other" ] && other=$model
        case "$model" in
            GT-BE19000|GT-BE19000AI) printf '%s\n' "$model"; return 0 ;;
        esac
    done
    [ -n "$other" ] || { asus_error 'Cannot identify an ASUS router OS.'; return 1; }
    printf 'ASUS NFQWS2 WARNING: %s has not been tested. Use at your own risk; developers accept no liability for damage, data loss or connectivity loss.\n' "$other" >&2
    printf '%s\n' "$other"
}

asus_interface_valid() {
    case "$1" in ''|*[!a-zA-Z0-9_.:-]*) return 1;; esac
    [ "${#1}" -le 15 ] && ip link show dev "$1" >/dev/null 2>&1
}

asus_interfaces() {
    local iface unit proto found=''
    if [ -n "$ISP_INTERFACE" ]; then
        for iface in $ISP_INTERFACE; do
            asus_interface_valid "$iface" || { asus_error "Invalid/missing interface: $iface"; return 1; }
            printf '%s\n' "$iface"
        done
        return 0
    fi
    for unit in 0 1; do
        [ "$(nvram get "wan${unit}_state_t" 2>/dev/null)" = 2 ] || continue
        proto=$(nvram get "wan${unit}_proto" 2>/dev/null)
        case "$proto" in
            pppoe|pptp|l2tp) iface=$(nvram get "wan${unit}_pppoe_ifname" 2>/dev/null) ;;
            *) iface=$(nvram get "wan${unit}_ifname" 2>/dev/null) ;;
        esac
        if ! asus_interface_valid "$iface"; then
            iface=$(nvram get "wan${unit}_gw_ifname" 2>/dev/null)
        fi
        if asus_interface_valid "$iface"; then
            case " $found " in *" $iface "*) ;; *) found="$found $iface"; printf '%s\n' "$iface";; esac
        fi
    done
    [ -n "$found" ]
}

asus_validate() {
    local list addr
    case "$NFQUEUE_NUM" in ''|*[!0-9]*) asus_error 'NFQUEUE_NUM must be 0..65535'; return 1;; esac
    [ "$NFQUEUE_NUM" -le 65535 ] 2>/dev/null || { asus_error 'NFQUEUE_NUM must be 0..65535'; return 1; }
    case "$IPV6_ENABLED" in 0|1) ;; *) asus_error 'IPV6_ENABLED must be 0 or 1'; return 1;; esac
    for list in "$TCP_PORTS" "$UDP_PORTS"; do
        case "$list" in ''|*[!0-9,:]*) asus_error 'Invalid port list'; return 1;; esac
    done
    case "$ASUS_CLIENT_MODE" in
        all|exclude) ;;
        include) set -- $ASUS_CLIENTS4 $ASUS_CLIENTS6
            [ "$#" -gt 0 ] || { asus_error 'Include mode needs client addresses'; return 1; } ;;
        *) asus_error 'ASUS_CLIENT_MODE must be all, include or exclude'; return 1;;
    esac
    for addr in $ASUS_CLIENTS4; do
        case "$addr" in *[!0-9./]*) asus_error "Invalid IPv4 client: $addr"; return 1;; esac
    done
    for addr in $ASUS_CLIENTS6; do
        case "$addr" in *[!0-9a-fA-F:/]*) asus_error "Invalid IPv6 client: $addr"; return 1;; esac
    done
    return 0
}

asus_load_modules() {
    local module path
    for module in nfnetlink nfnetlink_queue xt_NFQUEUE xt_connbytes xt_conntrack xt_multiport xt_mark; do
        modprobe "$module" 2>/dev/null && continue
        path=$(find "/lib/modules/$(uname -r)" -name "$module.ko" -o -name "$module.ko.gz" 2>/dev/null | head -n 1)
        [ -z "$path" ] || insmod "$path" 2>/dev/null
    done
    if [ ! -e /proc/net/netfilter/nfnetlink_queue ] && command -v asus_load_legacy_module >/dev/null 2>&1; then
        asus_load_legacy_module || :
    fi
    # Built-in modules need not appear in lsmod. The probe below is authoritative.
    return 0
}

asus_probe_restore() {
    local cmd=$1
    if command -v asus_xtables >/dev/null 2>&1; then
        asus_xtables "$cmd-restore" --noflush
    else
        "$cmd-restore" --noflush
    fi
}

asus_probe_family() (
    local cmd=$1 chain="nfqa_probe_$$" addr clients acct created=0 saved
    case "$cmd" in
        iptables) clients=$ASUS_CLIENTS4 ;;
        ip6tables) clients=$ASUS_CLIENTS6 ;;
        *) exit 1 ;;
    esac
    acct=$(sysctl -n net.netfilter.nf_conntrack_acct 2>/dev/null) || exit 1
    case "$acct" in 0|1) ;; *) exit 1;; esac
    # Old xt_connbytes silently enables accounting when a detached rule is
    # inserted. Restore the probe's side effect before start takes its snapshot.
    trap 'if [ "$created" = 1 ]; then "$cmd" -w -t mangle -F "$chain" >/dev/null 2>&1; "$cmd" -w -t mangle -X "$chain"; fi
          if [ "$acct" = 0 ] && [ "$(sysctl -n net.netfilter.nf_conntrack_acct 2>/dev/null)" = 1 ]; then sysctl -w net.netfilter.nf_conntrack_acct=0 >/dev/null; fi' EXIT
    "$cmd" -w -t mangle -N "$chain" || exit 1
    created=1
    for addr in $clients; do
        "$cmd" -w -t mangle -A "$chain" -m conntrack --ctorigsrc "$addr" -j RETURN || exit 1
    done
    "$cmd" -w -t mangle -A "$chain" -m mark --mark 0x40000000/0x40000000 -j RETURN || exit 1
    "$cmd" -w -t mangle -A "$chain" -p tcp -m multiport --dports "$TCP_PORTS" \
        -m conntrack --ctdir ORIGINAL -m connbytes --connbytes-dir original \
        --connbytes-mode packets --connbytes 1:15 -j NFQUEUE --queue-num "$NFQUEUE_NUM" --queue-bypass || exit 1
    "$cmd" -w -t mangle -A "$chain" -p udp -m multiport --dports "$UDP_PORTS" \
        -j NFQUEUE --queue-num "$NFQUEUE_NUM" --queue-bypass || exit 1
    # A working CLI alone does not establish compatibility of its restore
    # counterpart. Round-trip only this detached chain, never a live hook.
    saved=$("$cmd" -w -t mangle -S "$chain") || exit 1
    {
        printf '*mangle\n:%s - [0:0]\n-F %s\n' "$chain" "$chain"
        printf '%s\n' "$saved" | sed -n '/^-A /p'
        printf 'COMMIT\n'
    } | asus_probe_restore "$cmd" || exit 1
)

asus_probe_ping() {
    case "$1" in
        iptables) /opt/libexec/nfqws2-asus/busybox ping -c 1 -W 1 "$2" ;;
        ip6tables) /opt/libexec/nfqws2-asus/busybox ping6 -c 1 -W 1 "$2" ;;
        *) return 1 ;;
    esac
}

# Classify the live match, not a model name or uname string. Only a local
# echo request visits these counting rules; no packets are queued or dropped.
asus_probe_direction() (
    local cmd=$1 chain="nfqa_dir_$$" addr proto option created=0 hooked=0 counts
    case "$cmd" in
        iptables) addr=127.254.0.2; proto=icmp; option=--icmp-type ;;
        ip6tables) addr=::1; proto=ipv6-icmp; option=--icmpv6-type ;;
        *) exit 1 ;;
    esac
    trap 'if [ "$hooked" = 1 ]; then "$cmd" -w -t mangle -D OUTPUT -d "$addr" -p "$proto" "$option" echo-request -j "$chain" >/dev/null; fi
          if [ "$created" = 1 ]; then "$cmd" -w -t mangle -F "$chain" >/dev/null; "$cmd" -w -t mangle -X "$chain" >/dev/null; fi' EXIT
    "$cmd" -w -t mangle -N "$chain" || exit 1
    created=1
    "$cmd" -w -t mangle -A "$chain" || exit 1
    "$cmd" -w -t mangle -A "$chain" -m conntrack --ctdir ORIGINAL || exit 1
    "$cmd" -w -t mangle -A "$chain" -m conntrack --ctdir REPLY || exit 1
    "$cmd" -w -t mangle -I OUTPUT 1 -d "$addr" -p "$proto" "$option" echo-request -j "$chain" || exit 1
    hooked=1
    asus_probe_ping "$cmd" "$addr" >/dev/null 2>&1 || exit 1
    counts=$("$cmd" -w -t mangle -L "$chain" -nvx) || exit 1
    printf '%s\n' "$counts" | awk '
        NR==3 {all=$1} NR==4 {orig=$1} NR==5 {reply=$1}
        END {
            if (all+0>0 && orig==all && reply==0) print "normal";
            else if (all+0>0 && orig==0 && reply==all) print "reverse";
            else exit 1;
        }'
)

# Emit only this service's chains, suitable for iptables-restore --noflush.
# Root PREROUTING/POSTROUTING jumps are attached separately and idempotently.
asus_rules() {
    local family=$1 table=$2 chain iface addr clients dest direction proto ports ct_original=ORIGINAL ct_reply=REPLY observed
    case "$family" in
        4) clients=$ASUS_CLIENTS4 ;;
        6) clients=$ASUS_CLIENTS6 ;;
        *) return 1 ;;
    esac
    case "$family" in 4) observed=${ASUS_CT4:-normal};; 6) observed=${ASUS_CT6:-normal};; esac
    case "$observed" in normal) ;; reverse) ct_original=REPLY; ct_reply=ORIGINAL;; *) return 1;; esac
    if [ "$table" = nat ]; then
        [ "$family" = 4 ] || return 1
        printf '*nat\n:nfqa_nat - [0:0]\n-F nfqa_nat\n'
        for iface in $ASUS_WAN; do
            printf '%s\n' "-A nfqa_nat -o $iface -m mark --mark 0x40000000/0x40000000 -p udp -j MASQUERADE"
        done
        printf 'COMMIT\n'; return 0
    fi
    printf '*mangle\n'
    for chain in pre post in out; do printf ':nfqa_%s - [0:0]\n-F nfqa_%s\n' "$chain" "$chain"; done
    for chain in pre post; do
        printf '%s\n' "-A nfqa_$chain -m mark --mark 0x40000000/0x40000000 -j RETURN"
        if [ "$ASUS_CLIENT_MODE" = exclude ]; then
            for addr in $clients; do
                printf '%s\n' "-A nfqa_$chain -m conntrack --ctorigsrc $addr -j RETURN"
            done
        fi
        if [ "$chain" = post ]; then dest=out; direction='-o'; proto=$ct_original
        else dest=in; direction='-i'; proto=$ct_reply; fi
        for iface in $ASUS_WAN; do
            if [ "$ASUS_CLIENT_MODE" = include ]; then
                for addr in $clients; do
                    printf '%s\n' "-A nfqa_$chain $direction $iface -m conntrack --ctdir $proto --ctorigsrc $addr -j nfqa_$dest"
                done
            else
                printf '%s\n' "-A nfqa_$chain $direction $iface -m conntrack --ctdir $proto -j nfqa_$dest"
            fi
        done
    done
    for dest in out in; do
        if [ "$dest" = out ]; then direction=original; ports=--dports
        else direction=reply; ports=--sports; fi
        for proto in tcp udp; do
            [ "$proto" = tcp ] && clients=$TCP_PORTS || clients=$UDP_PORTS
            printf '%s\n' "-A nfqa_$dest -p $proto -m multiport $ports $clients -m connbytes --connbytes-dir $direction --connbytes-mode packets --connbytes 1:15 -j NFQUEUE --queue-num $NFQUEUE_NUM --queue-bypass"
        done
        for proto in 'FIN FIN' 'RST RST'; do
            printf '%s\n' "-A nfqa_$dest -p tcp -m multiport $ports $TCP_PORTS --tcp-flags $proto -j NFQUEUE --queue-num $NFQUEUE_NUM --queue-bypass"
        done
    done
    printf '%s\n' "-A nfqa_in -p tcp -m multiport --sports $TCP_PORTS --tcp-flags SYN,ACK SYN,ACK -j NFQUEUE --queue-num $NFQUEUE_NUM --queue-bypass"
    printf 'COMMIT\n'
}

asus_detach_family() {
    local cmd=$1 table parent chain clients
    case "$cmd" in iptables|ip6tables) ;; *) return 1;; esac
    for table in mangle nat; do
        [ "$cmd" = ip6tables ] && [ "$table" = nat ] && continue
        for parent in PREROUTING POSTROUTING; do
            if [ "$table" = nat ]; then
                [ "$parent" = PREROUTING ] && continue
                chain=nfqa_nat
            elif [ "$parent" = PREROUTING ]; then chain=nfqa_pre
            else chain=nfqa_post; fi
            while "$cmd" -w -t "$table" -C "$parent" -j "$chain" >/dev/null 2>&1; do
                "$cmd" -w -t "$table" -D "$parent" -j "$chain" || return 1
            done
        done
        if [ "$table" = nat ]; then clients=nfqa_nat
        else clients='nfqa_pre nfqa_post nfqa_in nfqa_out'; fi
        for chain in $clients; do "$cmd" -w -t "$table" -F "$chain" 2>/dev/null; done
        for chain in $clients; do "$cmd" -w -t "$table" -X "$chain" 2>/dev/null; done
    done
    return 0
}
