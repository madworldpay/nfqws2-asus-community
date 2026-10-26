# Native panel listener policy; configuration is root-owned UCI, never HTTP input.
nfqws_web_ipv4() {
    printf '%s\n' "$1" | awk -F. 'NF!=4{exit 1} {for(i=1;i<=4;i++)if($i!~/^[0-9]+$/||length($i)>3||$i>255)exit 1; if($0=="0.0.0.0")exit 1}'
}

nfqws_web_address() {
    if nfqws_web_ipv4 "$1"; then
        NFQWS_WEB_CUSTOM=1
        NFQWS_WEB_ADDRESSES="$NFQWS_WEB_ADDRESSES $1"
    else NFQWS_WEB_INVALID=1; fi
}

nfqws_web_listeners() {
    local port network address NFQWS_WEB_CUSTOM=0 NFQWS_WEB_INVALID=0 NFQWS_WEB_ADDRESSES=''
    config_get port main port 90
    case "$port" in ''|*[!0-9]*) return 1;; esac
    [ "$port" -ge 1024 ] && [ "$port" -le 65535 ] || { [ "$port" = 90 ] || return 1; }
    config_list_foreach main listen nfqws_web_address
    [ "$NFQWS_WEB_INVALID" = 0 ] || return 1
    if [ "$NFQWS_WEB_CUSTOM" = 0 ]; then
        config_get network main network lan
        case "$network" in ''|*[!a-zA-Z0-9_]*) return 1;; esac
        for address in $(ubus call "network.interface.$network" status 2>/dev/null | jsonfilter -e '@["ipv4-address"][*].address'); do
            nfqws_web_address "$address"
        done
    fi
    [ "$NFQWS_WEB_INVALID" = 0 ] || return 1
    for address in 127.0.0.1 $NFQWS_WEB_ADDRESSES; do printf '%s:%s\n' "$address" "$port"; done | sort -u
}

nfqws_web_private_directory() {
    [ ! -L "$1" ] || return 1
    if [ ! -e "$1" ]; then (umask 077; mkdir "$1") || return 1; fi
    [ -d "$1" ] && [ "$(LC_ALL=C ls -dn "$1" | awk '{print $1,$3}')" = 'drwx------ 0' ]
}
