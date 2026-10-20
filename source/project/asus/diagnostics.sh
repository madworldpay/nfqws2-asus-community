#!/bin/sh
# Read-only. Never source user configuration, run preflight or acquire a lock.
asus_diagnostic_queue() {
    [ -r "$1" ] && [ -f "$1" ] || { echo null; return; }
    awk '
    /^[ \t]*(export[ \t]+)?NFQUEUE_NUM[ \t]*=/ {
        count++; value=$0; sub(/^[^=]*=[ \t]*/, "", value)
        sub(/[ \t]+#.*/, "", value); sub(/[ \t]+$/, "", value)
        quote=substr(value,1,1)
        if (quote == "\047" || quote == "\042") {
            if (substr(value,length(value),1) != quote) { invalid=1; next }
            value=substr(value,2,length(value)-2)
        }
        if (value !~ /^[0-9]+$/ || value+0 > 65535) invalid=1
        number=value+0
    }
    END { if (count == 0) print "300"; else if (count == 1 && !invalid) printf "%.0f\n", number; else print "null" }
    ' "$1" 2>/dev/null || echo null
}

asus_diagnostic_process() {
    local pid exe binary
    [ -r /proc/self/status ] || { echo null; return; }
    if [ ! -e "$PIDFILE" ]; then echo false; return; fi
    [ -r "$PIDFILE" ] && [ -f "$PIDFILE" ] || { echo null; return; }
    pid=$(cat "$PIDFILE" 2>/dev/null) || { echo null; return; }
    case "$pid" in ''|*[!0-9]*) echo false; return;; esac
    [ "$pid" -gt 1 ] 2>/dev/null || { echo false; return; }
    [ -d "/proc/$pid" ] || { echo false; return; }
    exe=$(readlink "/proc/$pid/exe" 2>/dev/null) || { echo null; return; }
    binary=$(readlink -f "$NFQWS_BIN" 2>/dev/null) || { echo null; return; }
    case "$exe" in "$binary"|"$binary (deleted)") echo true;; *) echo false;; esac
}

asus_diagnostics_json() {
    local q=$1 proc_root=${2:-/proc} sys_root=${3:-/sys} ark_root=${4:-/usr/ark}
    local loaded=unknown present=unknown queue_state=unknown sequence=null queue=null result
    if [ -d "$sys_root/module/ark" ]; then
        loaded=loaded
    elif [ -r "$proc_root/modules" ] && [ -f "$proc_root/modules" ] && [ -r "$sys_root/module" ] && [ -x "$sys_root/module" ]; then
        result=$(awk '$1 == "ark" { found=1 } END { print found ? "loaded" : "unloaded" }' "$proc_root/modules" 2>/dev/null) && loaded=$result
    fi
    if [ "$loaded" = loaded ]; then present=present
    elif [ -r "$ark_root" ] && [ -x "$ark_root" ]; then
        present=absent
        for result in ark.ko ark_service arkctl; do
            [ ! -f "$ark_root/$result" ] || present=present
        done
    elif [ ! -e "$ark_root" ] && [ -r "${ark_root%/*}" ] && [ "$loaded" = unloaded ]; then present=absent
    fi
    case "$q" in ''|*[!0-9]*) ;;
        *) queue=$(awk -v q="$q" 'BEGIN { if (q+0<=65535) printf "%.0f",q; else print "null" }');;
    esac
    if [ "$queue" != null ] && [ -r "$proc_root/net/netfilter/nfnetlink_queue" ] && [ -f "$proc_root/net/netfilter/nfnetlink_queue" ]; then
        result=$(awk -v q="$queue" '
        $1+0 == q && $1 ~ /^[0-9]+$/ {
            found++
            if (NF != 9) invalid=1
            for (i=1;i<=NF;i++) if ($i !~ /^[0-9]+$/) invalid=1
            if ($8+0 > 4294967295) invalid=1
            seq=$8+0
        }
        END {
            if (invalid || found>1) print "unknown null"
            else if (found) printf "bound %.0f\n",seq
            else print "unbound null"
        }' "$proc_root/net/netfilter/nfnetlink_queue" 2>/dev/null) || result='unknown null'
        queue_state=${result%% *}; sequence=${result#* }
    fi
    case "${ASUS_DIAGNOSTIC_PROCESS:-null}" in true|false|null) ;; *) ASUS_DIAGNOSTIC_PROCESS=null;; esac
    printf '{"ark":{"present":"%s","loaded":"%s"},"nfqueue":{"queue_number":%s,"state":"%s","sequence":%s},"process_running":%s}\n' "$present" "$loaded" "$queue" "$queue_state" "$sequence" "${ASUS_DIAGNOSTIC_PROCESS:-null}"
}
