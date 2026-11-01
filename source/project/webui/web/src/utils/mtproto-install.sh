# Independent Telegram proxy. Source: Flowseal/tg-ws-proxy (MIT).
# This file is included in the generated, reviewable installation command.
PATH=/opt/bin:/opt/sbin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
umask 077
# Merlin omits several BusyBox applet symlinks. Use the package's full runtime.
if [ -x /opt/libexec/nfqws2-asus/busybox ]; then
    mtbb=/opt/libexec/nfqws2-asus/busybox
    id() { "$mtbb" id "$@"; }
    sha256sum() { "$mtbb" sha256sum "$@"; }
    mktemp() { "$mtbb" mktemp "$@"; }
    tar() { "$mtbb" tar "$@"; }
    cp() { "$mtbb" cp "$@"; }
    chmod() { "$mtbb" chmod "$@"; }
    mkdir() { "$mtbb" mkdir "$@"; }
    rm() { "$mtbb" rm "$@"; }
    sleep() { "$mtbb" sleep "$@"; }
fi
msg() { if [ "$NFQWS_MT_LANG" = ru ]; then printf '%s\n' "$2"; else printf '%s\n' "$1"; fi; }
fail() { msg "$1" "$2" >&2; exit 1; }
findexe() { for d in /opt/bin /opt/sbin /usr/bin /usr/sbin /bin /sbin; do if [ -x "$d/$1" ]; then printf '%s\n' "$d/$1"; return 0; fi; done; return 1; }
root=''
unit=''
container=''
work=''
committed=no
cleanup() {
    rc=$?
    trap - 0 HUP INT TERM
    if [ "$committed" != yes ]; then
        if [ -n "$container" ]; then docker rm -f "$container" >/dev/null 2>&1 || :; fi
        if [ -n "$unit" ]; then
            if [ "$NFQWS_MT_METHOD" = linux ]; then
                systemctl disable --now nfqws-mtproto.service >/dev/null 2>&1 || :
            elif [ -x "$unit" ]; then "$unit" stop >/dev/null 2>&1 || :; fi
            rm -f "$unit"
            if [ "$NFQWS_MT_METHOD" = linux ]; then systemctl daemon-reload >/dev/null 2>&1 || :; fi
        fi
        if [ -n "$root" ]; then rm -rf "$root"; fi
    fi
    if [ -n "$work" ]; then rm -rf "$work"; fi
    exit "$rc"
}
trap cleanup 0
trap 'exit 130' INT
trap 'exit 143' HUP TERM

if [ "$NFQWS_MT_METHOD" = docker ]; then
    findexe docker >/dev/null || fail 'Docker CLI is missing. Run this on the Docker host.' 'Нет Docker CLI. Выполните команду на устройстве с Docker.'
    docker info >/dev/null 2>&1 || fail 'Docker daemon is unavailable.' 'Служба Docker недоступна.'
    if docker container inspect nfqws-mtproto >/dev/null 2>&1; then
        fail 'nfqws-mtproto already exists; nothing was changed.' 'Контейнер nfqws-mtproto уже существует; ничего не изменено.'
    fi
else
    [ "$(id -u)" = 0 ] || fail 'Run this command as root (sudo sh).' 'Выполните команду от root (sudo sh).'
    [ "$NFQWS_MT_PORT" -ge 1024 ] || fail 'Native service requires a port >= 1024.' 'Для запуска без Docker выберите порт от 1024.'
    if [ "$NFQWS_MT_METHOD" = entware ]; then
        [ -x /opt/bin/opkg ] && [ -d /opt/etc/init.d ] || fail 'Entware is required.' 'Нужен установленный Entware.'
        candidate=/opt/share/nfqws-mtproto
        service=/opt/etc/init.d/S98nfqws-mtproto
    else
        [ -d /run/systemd/system ] && findexe systemctl >/dev/null || fail 'This method requires Linux with systemd. On ASUS choose Entware.' 'Нужен Linux с systemd. Для ASUS выберите Entware.'
        candidate=/usr/local/share/nfqws-mtproto
        service=/etc/systemd/system/nfqws-mtproto.service
        if systemctl cat nfqws-mtproto.service >/dev/null 2>&1; then
            fail 'nfqws-mtproto already exists; nothing was changed.' 'Служба nfqws-mtproto уже существует; ничего не изменено.'
        fi
    fi
    [ ! -e "$candidate" ] && [ ! -L "$candidate" ] && [ ! -e "$service" ] && [ ! -L "$service" ] || fail 'MTProto files already exist; nothing was changed.' 'Файлы MTProto уже существуют; ничего не изменено.'
fi

if [ "$NFQWS_MT_METHOD" != docker ]; then
curlbin=$(findexe curl) || fail 'curl is required.' 'Нужна программа curl.'
printf '' | sha256sum >/dev/null 2>&1 || fail 'sha256sum is required.' 'Нужна программа sha256sum.'
work=$(mktemp -d /tmp/nfqws-mtproto.XXXXXX)
msg 'Downloading verified proxy source...' 'Скачивание исходников прокси с проверкой...'
"$curlbin" -fL --connect-timeout 10 --max-time 120 --retry 2 \
    'https://codeload.github.com/Flowseal/tg-ws-proxy/tar.gz/50d539c718f1689c0437b7cf623e5995018c01e3' -o "$work/source.tgz"
printf '%s  %s\n' '87a38c235d7a4a66d8a3fa50d64e42cc962c11c210a9e65df1469302a6521613' "$work/source.tgz" | sha256sum -c -
mkdir "$work/source"
tar -xzf "$work/source.tgz" -C "$work/source"
source="$work/source/tg-ws-proxy-50d539c718f1689c0437b7cf623e5995018c01e3"
fi

if [ "$NFQWS_MT_METHOD" = docker ]; then
    image='@@MTPROTO_DOCKER_IMAGE@@'
    msg 'Downloading the pinned Docker image...' 'Загрузка закреплённого образа Docker...'
    docker pull "$image"
    container=$(docker create --name nfqws-mtproto --restart unless-stopped \
        --log-opt max-size=5m --log-opt max-file=2 \
        --cap-drop ALL --security-opt no-new-privileges:true \
        -p "$NFQWS_MT_PORT:1443" -e "PROXY_SECRET=$NFQWS_MT_KEY" \
        -e PROXY_HOST=0.0.0.0 -e PROXY_PORT=1443 \
        -e 'PROXY_DC_IPS=2:149.154.167.220 4:149.154.167.220' "$image")
    docker start "$container" >/dev/null
    sleep 3
    [ "$(docker inspect --format '{{.State.Running}}' "$container")" = true ] || fail 'Proxy stopped. Check Docker logs.' 'Прокси остановился. Проверьте журнал Docker.'
    docker exec "$container" /opt/venv/bin/python -c 'import socket; socket.create_connection(("127.0.0.1",1443),timeout=3).close()' || fail 'Proxy is not listening; installation rolled back.' 'Прокси не принимает подключения; установка отменена.'
else
    mkdir "$candidate"
    root=$candidate
    chmod 755 "$root"
    mkdir "$root/app"
    cp -R "$source/proxy" "$source/utils" "$source/LICENSE" "$root/app/"
    chmod -R a+rX "$root/app"
    if [ "$NFQWS_MT_METHOD" = entware ]; then
        if [ ! -x /opt/bin/python3 ]; then
            /opt/bin/opkg update
            /opt/bin/opkg install python3 python3-pip
        fi
        python=/opt/bin/python3
        # Missing pure Python modules stay in our directory; existing modules are reused.
        if ! "$python" -c 'import httpx,h2,certifi' >/dev/null 2>&1; then
            "$python" -m pip --version >/dev/null 2>&1 || /opt/bin/opkg install python3-pip
            "$python" -m pip install --disable-pip-version-check --timeout 15 --retries 2 \
                --target "$root/app/vendor" 'httpx[http2]==0.28.1' certifi
            chmod -R a+rX "$root/app/vendor"
        fi
    else
        python=$(findexe python3) || fail 'Install Python 3 and python3-venv first.' 'Сначала установите Python 3 и python3-venv.'
        "$python" -m venv "$root/venv" || fail 'Install python3-venv and retry.' 'Установите python3-venv и повторите команду.'
        python="$root/venv/bin/python"
        "$python" -m pip install --disable-pip-version-check --timeout 15 --retries 2 'cryptography==46.0.5' 'httpx[http2]==0.28.1' certifi
        chmod -R a+rX "$root/venv"
    fi
    "$python" - "$root" "$NFQWS_MT_PORT" "$NFQWS_MT_KEY" <<'PY'
import json, os, pwd, socket, sys
root, port, secret = sys.argv[1:]
assert sys.version_info >= (3, 8), 'Python 3.8+ required'
pwd.getpwnam('nobody')
sys.path[:0] = [root + '/app', root + '/app/vendor']
from proxy._aes import Cipher, algorithms, modes
import httpx, certifi, h2
with socket.socket() as s:
    s.bind(('0.0.0.0', int(port)))
with open(root + '/config.json', 'x') as f:
    json.dump({'port': int(port), 'secret': secret}, f)
os.chmod(root + '/config.json', 0o600)
PY
    cat > "$root/run.py" <<'PY'
import json, os, pwd, signal, sys
root = os.path.dirname(os.path.realpath(__file__))
with open(root + '/config.json') as f:
    config = json.load(f)
sys.path[:0] = [root + '/app', root + '/app/vendor']
signal.signal(signal.SIGHUP, signal.SIG_IGN)
user = pwd.getpwnam('nobody')
os.setgroups([])
os.setgid(user.pw_gid)
os.setuid(user.pw_uid)
sys.dont_write_bytecode = True
# asyncio binds both available address families when host is empty.
sys.argv = ['nfqws-mtproto', '--host', '', '--port', str(config['port']), '--secret', config['secret']]
from proxy.tg_ws_proxy import main
main()
PY
    chmod 644 "$root/run.py"
    if [ "$NFQWS_MT_METHOD" = entware ]; then
        # The service only stops the process whose command line matches this runner.
        cat > "$work/service" <<'SH'
#!/bin/sh
root=/opt/share/nfqws-mtproto
pidfile=/opt/var/run/nfqws-mtproto.pid
log=/opt/var/log/nfqws-mtproto.log
PATH=/opt/bin:/opt/sbin:/usr/sbin:/usr/bin:/sbin:/bin
if [ -x /opt/libexec/nfqws2-asus/busybox ]; then
    tr() { /opt/libexec/nfqws2-asus/busybox tr "$@"; }
    grep() { /opt/libexec/nfqws2-asus/busybox grep "$@"; }
fi
owned() {
    [ -f "$pidfile" ] || return 1
    read -r pid < "$pidfile"
    case "$pid" in ''|*[!0-9]*) return 1;; esac
    [ -r "/proc/$pid/cmdline" ] || return 1
    tr '\000' '\n' < "/proc/$pid/cmdline" | grep -Fx "$root/run.py" >/dev/null
}
case "${1:-}" in
start)
    owned && exit 0
    mkdir -p /opt/var/run /opt/var/log
    umask 077
    /opt/bin/python3 "$root/run.py" >> "$log" 2>&1 < /dev/null &
    echo $! > "$pidfile"
    ;;
stop)
    if owned; then kill "$pid"; fi
    rm -f "$pidfile"
    ;;
restart) "$0" stop; sleep 1; "$0" start;;
status) if owned && kill -0 "$pid" 2>/dev/null; then echo MTProto_RUNNING; else echo MTProto_STOPPED; exit 1; fi;;
*) echo 'start|stop|restart|status'; exit 1;;
esac
SH
        # Exclusive publication prevents a concurrent installer overwriting a service.
        (set -C; cat "$work/service" > "$service")
        unit=$service
        chmod 755 "$unit"
        "$unit" start
        sleep 3
        "$unit" status
    else
        cat > "$work/service" <<EOF
[Unit]
Description=Telegram MTProto (Flowseal tg-ws-proxy)
After=network-online.target
Wants=network-online.target
[Service]
ExecStart=$python $root/run.py
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
[Install]
WantedBy=multi-user.target
EOF
        (set -C; cat "$work/service" > "$service")
        unit=$service
        chmod 644 "$unit"
        systemctl daemon-reload
        systemctl enable --now nfqws-mtproto.service
        sleep 3
        systemctl is-active --quiet nfqws-mtproto.service
    fi
fi
committed=yes
msg 'Proxy started. Test the connection in Telegram:' 'Прокси запущен. Проверьте подключение в Telegram:'
printf '%s\n' "$NFQWS_MT_LINK"
