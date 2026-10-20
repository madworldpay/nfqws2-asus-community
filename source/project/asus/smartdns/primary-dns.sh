#!/bin/sh
# Read-only firmware process proof. Fixed fields only, no eval or shell state.
sd_primary_bb=/bin/busybox
sd_primary_exe=/usr/sbin/dnsmasq
sd_primary_config=/tmp/etc/dnsmasq.conf
sd_primary_default=/etc/dnsmasq.conf

sd_primary_identity() {
    local pid parent line rest ticks after exe count found parent_name default_ok
    count=0;found=;default_ok=0
    [ "$("$sd_primary_bb" readlink -f "$sd_primary_default" 2>/dev/null)" = "$sd_primary_config" ] && default_ok=1
    for pid in $("$sd_primary_bb" pidof dnsmasq 2>/dev/null); do
        case "$pid" in ''|*[!0-9]*) continue;; esac
        [ "$pid" -gt 1 ] 2>/dev/null || continue
        IFS= read -r line 2>/dev/null < "/proc/$pid/stat" || continue
        rest=${line##*) };set -- $rest
        [ "${1:-Z}" != Z ] && [ -n "${20:-}" ] || continue
        parent=${2};ticks=${20};parent_name=
        if [ -r "/proc/$parent/comm" ]; then IFS= read -r parent_name < "/proc/$parent/comm" || :;fi
        [ "$parent_name" != dnsmasq ] || continue
        exe=$("$sd_primary_bb" readlink "/proc/$pid/exe" 2>/dev/null) || continue
        [ "$exe" = "$sd_primary_exe" ] || continue
        if ! "$sd_primary_bb" tr '\000' '\n' < "/proc/$pid/cmdline" | "$sd_primary_bb" awk -v config="$sd_primary_config" -v native="$sd_primary_default" -v default_ok="$default_ok" '
            NR==1 {if ($0!~/(^|\/)dnsmasq$/) bad=1;next}
            pending {if ($0!=config && !($0==native && default_ok==1)) bad=1;explicit=1;pending=0;next}
            $0=="-C" || $0=="--conf-file" {pending=1;next}
            /^--conf-file=/ {v=$0;sub(/^--conf-file=/,"",v);if (v!=config && !(v==native && default_ok==1)) bad=1;explicit=1;next}
            /^--log-async(=[0-9]+)?$/ {next}
            {bad=1}
            END {exit (bad || pending || (!explicit && default_ok!=1))}'
        then continue;fi
        # Refuse a vanished/reused PID between reading argv and returning it.
        IFS= read -r line 2>/dev/null < "/proc/$pid/stat" || continue
        rest=${line##*) };set -- $rest;after=${20:-}
        [ "${1:-Z}" != Z ] && [ "$after" = "$ticks" ] || continue
        count=$((count+1));found="$pid $ticks"
    done
    [ "$count" = 1 ] || return 1
    printf '%s\n' "$found"
}

if [ "${0##*/}" = primary-dns.sh ]; then
    [ "$#" = 1 ] && [ "$1" = identity ] || exit 2
    sd_primary_identity;exit $?
fi
