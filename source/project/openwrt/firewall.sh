#!/bin/sh
# Native firewall4 integration. Never flush or edit another application's table.

nfqws_ports_valid() {
    [ -n "$1" ] && [ "${#1}" -le 2048 ] || return 1
    printf '%s\n' "$1" | awk -F, '
    { if(NF>128) exit 1; for(i=1;i<=NF;i++) {
        n=split($i,a,":"); if(n<1||n>2) exit 1;
        for(j=1;j<=n;j++) if(a[j]!~/^[0-9]+$/||a[j]+0<1||a[j]+0>65535) exit 1;
        if(n==2&&a[1]+0>a[2]+0) exit 1;
    }}'
}

nfqws_client_valid() {
    printf '%s\n' "$2" | awk -v family="$1" '
    {n=split($0,c,"/");if(n<1||n>2)exit 1;
     if(n==2&&(c[2]!~/^[0-9]+$/||c[2]+0>(family==4?32:128)))exit 1;
     if(family==4){if(split(c[1],a,".")!=4)exit 1;
       for(i=1;i<=4;i++)if(a[i]!~/^[0-9]+$/||a[i]+0>255)exit 1;
     }else if(c[1]!~/^[0-9a-fA-F:]+$/||length(c[1])>39||index(c[1],":")==0)exit 1;
    }'
}

nfqws_validate_rules() {
    local iface addr count=0
    case "$NFQUEUE_NUM" in ''|*[!0-9]*) return 1;; esac
    [ "${#NFQUEUE_NUM}" -le 5 ] && [ "$NFQUEUE_NUM" -le 65535 ] || return 1
    case "$IPV6_ENABLED" in 0|1) ;; *) return 1;; esac
    case "$ASUS_CLIENT_MODE" in all|include|exclude) ;; *) return 1;; esac
    [ "${#ASUS_CLIENTS4}" -le 16384 ] && [ "${#ASUS_CLIENTS6}" -le 16384 ] || return 1
    [ "$ASUS_CLIENT_MODE" != include ] || [ -n "$(printf '%s' "$ASUS_CLIENTS4$ASUS_CLIENTS6" | tr -d ' \t\r\n')" ] || return 1
    nfqws_ports_valid "$TCP_PORTS" && nfqws_ports_valid "$UDP_PORTS" || return 1
    [ -n "$NFQWS_WAN" ] && [ "${#NFQWS_WAN}" -le 1024 ] || return 1
    for iface in $NFQWS_WAN; do
        count=$((count+1)); [ "$count" -le 64 ] && [ "${#iface}" -le 15 ] || return 1
        case "$iface" in ''|*[!a-zA-Z0-9_.:-]*) return 1;; esac
    done
    for addr in $ASUS_CLIENTS4; do nfqws_client_valid 4 "$addr" || return 1; done
    for addr in $ASUS_CLIENTS6; do nfqws_client_valid 6 "$addr" || return 1; done
}

nfqws_client_set() {
    local name=$1 type=$2 values=$3 addr separator=''
    printf ' set %s { type %s; flags interval; auto-merge;\n' "$name" "$type"
    if [ -n "$values" ]; then
        printf ' elements = { '
        for addr in $values; do printf '%s%s' "$separator" "$addr"; separator=', '; done
        printf ' };\n'
    fi
    printf ' }\n'
}

nfqws_client_rules() {
    [ "$IPV6_ENABLED" = 1 ] || printf '  meta nfproto ipv6 return\n'
    case "$ASUS_CLIENT_MODE" in
        include)
            printf '  meta nfproto ipv4 ct original ip saddr != @clients4 return\n'
            printf '  meta nfproto ipv6 ct original ip6 saddr != @clients6 return\n';;
        exclude)
            printf '  meta nfproto ipv4 ct original ip saddr @clients4 return\n'
            printf '  meta nfproto ipv6 ct original ip6 saddr @clients6 return\n';;
    esac
}

nfqws_render_rules() (
    # Complete validation precedes stdout, so callers never see partial rules.
    set -f
    nfqws_validate_rules || { printf 'invalid_firewall_config\n' >&2; exit 1; }
    local iface separator='' chain direction portdir tcp udp
    tcp=$(printf '%s' "$TCP_PORTS" | tr : -)
    udp=$(printf '%s' "$UDP_PORTS" | tr : -)
    printf 'table inet nfqws2_native {\n comment "NFQWS2 native OpenWrt"\n'
    printf ' set uplinks { type ifname; elements = { '
    for iface in $NFQWS_WAN; do printf '%s"%s"' "$separator" "$iface"; separator=', '; done
    printf ' }; }\n'
    nfqws_client_set clients4 ipv4_addr "$ASUS_CLIENTS4"
    nfqws_client_set clients6 ipv6_addr "$ASUS_CLIENTS6"
    printf ' chain prerouting {\n  type filter hook prerouting priority mangle; policy accept;\n'
    printf '  meta mark & 0x40000000 != 0 return\n'
    printf '  iifname @uplinks ct direction reply jump reply\n }\n'
    printf ' chain postrouting {\n  type filter hook postrouting priority mangle; policy accept;\n'
    printf '  meta mark & 0x40000000 != 0 return\n'
    printf '  oifname @uplinks ct direction original jump original\n }\n'
    for direction in original reply; do
        [ "$direction" = original ] && portdir=dport || portdir=sport
        printf ' chain %s {\n' "$direction"
        nfqws_client_rules
        printf '  tcp %s { %s } ct %s packets 1-15 counter queue num %s bypass\n' "$portdir" "$tcp" "$direction" "$NFQUEUE_NUM"
        printf '  udp %s { %s } ct %s packets 1-15 counter queue num %s bypass\n' "$portdir" "$udp" "$direction" "$NFQUEUE_NUM"
        printf '  tcp %s { %s } tcp flags & (fin | rst) != 0 counter queue num %s bypass\n' "$portdir" "$tcp" "$NFQUEUE_NUM"
        if [ "$direction" = reply ]; then
            printf '  tcp sport { %s } tcp flags & (syn | ack) == (syn | ack) counter queue num %s bypass\n' "$tcp" "$NFQUEUE_NUM"
        fi
        printf ' }\n'
    done
    printf ' chain raw_udp_nat {\n  type nat hook postrouting priority srcnat + 1; policy accept;\n'
    printf '  meta nfproto ipv4 oifname @uplinks meta mark & 0x40000000 != 0 meta l4proto udp masquerade\n }\n}\n'
)

nfqws_firewall_owned() {
    local existing
    existing=$(nft list table inet nfqws2_native 2>/dev/null) || return 2
    printf '%s\n' "$existing" | grep -Fq 'comment "NFQWS2 native OpenWrt"'
}

nfqws_flow_probe() {
    local snapshot result lib=${NFQWS_LIB:-/usr/lib/nfqws2}
    snapshot=$(nft -j list table inet fw4 2>/dev/null) || { printf 'firewall4_unavailable\n' >&2; return 1; }
    [ "${#snapshot}" -le 2097152 ] || return 1
    result=$(printf '%s' "$snapshot" | /usr/bin/php-cgi -n -q -f "$lib/flow-cli.php") || return 1
    NFQWS_FLOW_STATE=$(printf '%s\n' "$result" | sed -n "s/^NFQWS_FLOW_STATE='\(none\|system\|managed\)'$/\1/p")
    NFQWS_FLOW_HANDLE=$(printf '%s\n' "$result" | sed -n "s/^NFQWS_FLOW_HANDLE='\([0-9]*\)'$/\1/p")
    NFQWS_FLOW_DEFINITION=$(printf '%s\n' "$result" | sed -n "s/^NFQWS_FLOW_DEFINITION='\([^']*\)'$/\1/p")
    case "$NFQWS_FLOW_STATE" in
        none) [ -z "$NFQWS_FLOW_HANDLE" ];;
        system|managed) case "$NFQWS_FLOW_HANDLE" in ''|*[!0-9]*) return 1;; esac
            [ "$NFQWS_FLOW_HANDLE" -gt 0 ] && [ -n "$NFQWS_FLOW_DEFINITION" ];;
        *) return 1;;
    esac
}

nfqws_flow_clients() {
    local family values addr separator rule
    [ "$IPV6_ENABLED" = 1 ] || printf 'add rule inet fw4 nfqws2_flow_scope meta nfproto ipv6 goto nfqws2_flow_add\n'
    [ "$ASUS_CLIENT_MODE" != all ] || return 0
    for family in 4 6; do
        [ "$family" = 4 ] && values=$ASUS_CLIENTS4 || values=$ASUS_CLIENTS6
        if [ -z "$values" ]; then
            [ "$ASUS_CLIENT_MODE" != include ] || printf 'add rule inet fw4 nfqws2_flow_scope meta nfproto ipv%s goto nfqws2_flow_add\n' "$family"
            continue
        fi
        [ "$family" = 4 ] && rule='ip' || rule='ip6'
        printf 'add rule inet fw4 nfqws2_flow_scope meta nfproto ipv%s ct original %s saddr ' "$family" "$rule"
        [ "$ASUS_CLIENT_MODE" != include ] || printf '!= '
        printf '{ '; separator=''
        for addr in $values; do printf '%s%s' "$separator" "$addr"; separator=', '; done
        printf ' } goto nfqws2_flow_add\n'
    done
}

nfqws_render_flow() (
    set -f
    local action=$1 chain iface separator='' tcp udp
    case "$NFQWS_FLOW_STATE" in none) exit 0;; system|managed) ;; *) exit 1;; esac
    case "$NFQWS_FLOW_HANDLE" in ''|*[!0-9]*) exit 1;; esac
    [ "$action" = stop ] || nfqws_validate_rules || exit 1
    if [ "$NFQWS_FLOW_STATE" = managed ]; then
        for chain in nfqws2_flow nfqws2_flow_scope nfqws2_flow_add; do printf 'flush chain inet fw4 %s\n' "$chain"; done
    fi
    if [ "$action" = stop ]; then
        [ "$NFQWS_FLOW_STATE" = managed ] || exit 0
        printf 'delete flowtable inet fw4 ft\n%s\n' "$NFQWS_FLOW_DEFINITION"
        printf 'replace rule inet fw4 forward handle %s meta l4proto { tcp, udp } flow offload @ft\n' "$NFQWS_FLOW_HANDLE"
        for chain in nfqws2_flow nfqws2_flow_scope nfqws2_flow_add; do printf 'delete chain inet fw4 %s\n' "$chain"; done
        exit 0
    fi
    if [ "$NFQWS_FLOW_STATE" = system ]; then
        for chain in nfqws2_flow nfqws2_flow_scope nfqws2_flow_add; do
            printf 'add chain inet fw4 %s { comment "NFQWS2 native OpenWrt"; }\n' "$chain"
        done
    fi
    printf 'replace rule inet fw4 forward handle %s jump nfqws2_flow comment "NFQWS2 native OpenWrt flow control"\n' "$NFQWS_FLOW_HANDLE"
    # Recreate only ft after removing all recognized references, in one transaction.
    printf 'delete flowtable inet fw4 ft\n%s\n' "$NFQWS_FLOW_DEFINITION"
    printf 'add rule inet fw4 nfqws2_flow ct direction reply return\n'
    printf 'add rule inet fw4 nfqws2_flow oifname { '
    for iface in $NFQWS_WAN; do printf '%s"%s"' "$separator" "$iface"; separator=', '; done
    printf ' } goto nfqws2_flow_scope\n'
    printf 'add rule inet fw4 nfqws2_flow goto nfqws2_flow_add\n'
    nfqws_flow_clients
    tcp=$(printf '%s' "$TCP_PORTS" | tr : -); udp=$(printf '%s' "$UDP_PORTS" | tr : -)
    # Offload only after BOTH capture windows, including a late reply, have passed.
    for chain in original reply; do
        printf 'add rule inet fw4 nfqws2_flow_scope tcp dport { %s } ct %s packets 0-15 return\n' "$tcp" "$chain"
        printf 'add rule inet fw4 nfqws2_flow_scope udp dport { %s } ct %s packets 0-15 return\n' "$udp" "$chain"
    done
    printf 'add rule inet fw4 nfqws2_flow_scope tcp dport { %s } tcp flags & (fin | rst) != 0 return\n' "$tcp"
    printf 'add rule inet fw4 nfqws2_flow_scope goto nfqws2_flow_add\n'
    printf 'add rule inet fw4 nfqws2_flow_add meta l4proto { tcp, udp } flow offload @ft\n'
)

nfqws_firewall_apply() {
    local owned=0 file run=${NFQWS_RUN:-/var/run/nfqws2-native}
    nfqws_firewall_owned || owned=$?
    [ "$owned" != 1 ] || { printf 'firewall_owner_conflict\n' >&2; return 1; }
    [ -d "$run" ] && [ ! -L "$run" ] || return 1
    nfqws_flow_probe || return 1
    file=$(mktemp "$run/rules.XXXXXX") || return 1
    (
        umask 077
        printf 'add table inet nfqws2_native\ndelete table inet nfqws2_native\n'
        nfqws_render_rules && nfqws_render_flow apply
    ) > "$file" || { rm -f "$file"; return 1; }
    nft -c -f "$file" || { rm -f "$file"; return 1; }
    # Both the old table deletion and new definition commit atomically.
    nft -f "$file" || { rm -f "$file"; return 1; }
    mv "$file" "$run/rules.nft"
}

nfqws_firewall_stop() {
    local owned=0 file run=${NFQWS_RUN:-/var/run/nfqws2-native}
    nfqws_firewall_owned || owned=$?
    case "$owned" in
        1) printf 'firewall_owner_conflict\n' >&2; return 1;;
    esac
    nfqws_flow_probe || return 1
    [ -d "$run" ] && [ ! -L "$run" ] || return 1
    file=$(mktemp "$run/stop.XXXXXX") || return 1
    (
        [ "$owned" = 2 ] || printf 'delete table inet nfqws2_native\n'
        nfqws_render_flow stop
    ) > "$file" || { rm -f "$file"; return 1; }
    nft -c -f "$file" && nft -f "$file"
    local rc=$?; rm -f "$file"; return "$rc"
}
