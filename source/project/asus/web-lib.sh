#!/bin/sh

web_runtime() {
    . /opt/lib/nfqws2-asus/target.sh || return 1
    . /opt/lib/nfqws2-asus/abi.sh || return 1
    local abi
    abi=$(asus_resolve_package_abi "$ASUS_PACKAGE_ARCH") || return 1
    WEB_BIN=/opt/libexec/nfqws-asus-web/lighttpd
    WEB_MODULE_DIR=/opt/lib/nfqws-asus-web/lighttpd
    if [ "$ASUS_PACKAGE_ARCH" = armv7 ]; then
        WEB_BIN=/opt/libexec/nfqws-asus-web/$abi/lighttpd
        WEB_MODULE_DIR=/opt/lib/nfqws-asus-web/lighttpd/$abi
    fi
}

web_lan() {
    local addr part oldifs
    addr=$(nvram get lan_ipaddr 2>/dev/null)
    case "$addr" in ''|*[!0-9.]*|0.*|127.*|255.255.255.255) return 1;; esac
    oldifs=$IFS; IFS=.; set -- $addr; IFS=$oldifs
    [ "$#" = 4 ] || return 1
    for part do
        [ -n "$part" ] && [ "$part" -le 255 ] 2>/dev/null || return 1
    done
    printf '%s\n' "$addr"
}

web_config() {
    cat <<EOF
server.modules = ( "mod_cgi", "mod_setenv", "mod_rewrite" )
server.document-root = "/opt/share/nfqws-asus-web"
server.bind = "$WEB_BIND"
server.port = 90
server.pid-file = "$WEB_RUN/pid"
server.errorlog = "$WEB_RUN/error.log"
server.max-connections = 16
server.max-request-size = 32768
# Bound dynamic buffering; any overflow stays in the private /tmp RAM runtime.
server.stream-request-body = 2
server.stream-response-body = 2
server.upload-dirs = ( "$WEB_RUN" )
server.max-keep-alive-requests = 16
index-file.names = ( "index.html" )
mimetype.assign = ( ".html" => "text/html", ".js" => "text/javascript", ".css" => "text/css", ".json" => "application/json", ".png" => "image/png", ".ico" => "image/x-icon", ".woff2" => "font/woff2" )
cgi.assign = ( ".php" => "/opt/lib/nfqws-asus-web/php-cgi.sh" )
static-file.exclude-extensions = ( ".php" )
setenv.set-environment = ( "PATH" => "/opt/sbin:/opt/bin:/opt/usr/bin:/usr/sbin:/usr/bin:/sbin:/bin" )
url.rewrite-if-not-file = ( "^/(.*)$" => "/index.html" )
# Package timestamps are normalized. Old HTML validators can otherwise survive
# an upgrade with the same file size and keep loading the previous frontend.
\$HTTP["url"] !~ "^/assets/" {
    static-file.etags = "disable"
    setenv.set-request-header = ( "If-None-Match" => "", "If-Modified-Since" => "" )
    setenv.set-response-header = ( "Cache-Control" => "no-store", "Last-Modified" => "" )
}
EOF
}

web_process_matches() {
    local pid exe binary args candidate
    pid=$(cat "$WEB_RUN/pid" 2>/dev/null)
    case "$pid" in ''|*[!0-9]*) return 1;; esac
    [ "$pid" -gt 1 ] && kill -0 "$pid" 2>/dev/null || return 1
    exe=$(readlink "/proc/$pid/exe" 2>/dev/null)
    binary=''
    for candidate do
        candidate=$(readlink -f "$candidate" 2>/dev/null) || continue
        case "$exe" in "$candidate"|"$candidate (deleted)") binary=$candidate; break;; esac
    done
    [ -n "$binary" ] || return 1
    args=$(tr '\000' ' ' < "/proc/$pid/cmdline")
    case "$args" in *" -f $WEB_RUN/lighttpd.conf "*) return 0;; esac
    return 1
}

web_running() { web_process_matches "$WEB_BIN"; }

web_owned_running() {
    # An upgrade or Entware ABI change can leave our previous binary running.
    # Only shipped paths AND our exact runtime config identify a process to stop.
    web_process_matches "$WEB_BIN" /opt/libexec/nfqws-asus-web/lighttpd \
        /opt/libexec/nfqws-asus-web/armv7-2.6/lighttpd \
        /opt/libexec/nfqws-asus-web/armv7-3.2/lighttpd
}

web_technical_channel() {
    local action=$1
    [ -d /tmp/nfqws2-technical-channel ] || [ -f /opt/etc/nfqws-asus-web/technical-channel/journal.json ] || return 0
    [ -f /opt/lib/nfqws2-asus/technical-channel/worker.php ] || return 1
    /opt/bin/php-cgi -d register_argc_argv=1 -q -f /opt/lib/nfqws2-asus/technical-channel/worker.php -- "$action" lifecycle 8>&- 9>&-
}

web_start() {
    local tries=0
    web_technical_channel recover || return 1
    web_running && return 0
    web_kill || return 1
    asus_model >/dev/null || return 1
    cru a nfqws_web_asus '* * * * * /opt/etc/init.d/S81nfqws-asus-web reconcile >/dev/null 2>&1' 8>&- 9>&- || return 1
    touch "$WEB_RUN/enabled"
    WEB_BIND=$(web_lan) || { echo 'Web panel waiting for a valid LAN IPv4 address.'; return 0; }
    mkdir -p "$WEB_RUN/sessions" || return 1
    chmod 700 "$WEB_RUN" "$WEB_RUN/sessions"
    web_config > "$WEB_RUN/lighttpd.conf"
    "$WEB_BIN" -m "$WEB_MODULE_DIR" -tt -f "$WEB_RUN/lighttpd.conf" || return 1
    "$WEB_BIN" -m "$WEB_MODULE_DIR" -f "$WEB_RUN/lighttpd.conf" 8>&- 9>&- || return 1
    while ! web_running && [ "$tries" -lt 3 ]; do sleep 1; tries=$((tries + 1)); done
    web_running || { asus_error 'Web server failed to start'; return 1; }
    printf '%s\n' "$WEB_BIND" > "$WEB_RUN/bind"
    echo "NFQWS2 ASUS web: http://$WEB_BIND:90"
}

web_kill() {
    local count=0
    if web_owned_running; then
        kill -TERM "$(cat "$WEB_RUN/pid")" || return 1
        while web_owned_running && [ "$count" -lt 5 ]; do sleep 1; count=$((count + 1)); done
        web_owned_running && return 1
    fi
    rm -f "$WEB_RUN/pid" "$WEB_RUN/bind"
}

web_stop() {
    web_technical_channel stop || return 1
    cru d nfqws_web_asus 8>&- 9>&- >/dev/null 2>&1
    rm -f "$WEB_RUN/enabled"
    web_kill
}

web_reconcile() {
    [ -f "$WEB_RUN/enabled" ] || return 0
    WEB_BIND=$(web_lan) || { web_kill; return $?; }
    if ! web_running || [ "$WEB_BIND" != "$(cat "$WEB_RUN/bind" 2>/dev/null)" ]; then
        web_kill && web_start
    fi
}
