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
    mv() { "$mtbb" mv "$@"; }
    rmdir() { "$mtbb" rmdir "$@"; }
    grep() { "$mtbb" grep "$@"; }
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
updating=no
previous_root=''
previous_unit=''
previous_container=''
previous_running=no
native_transition=no
removed_was_enabled=no
dc_ips='2:149.154.167.220 4:149.154.167.220'
pool_size=2
cf_domain=pclead.co.uk
refresh_link() {
    link_server=${NFQWS_MT_LINK%%&port=*}
    NFQWS_MT_LINK="$link_server&port=$NFQWS_MT_PORT&secret=dd$NFQWS_MT_KEY"
}
cleanup() {
    rc=$?
    trap - 0 HUP INT TERM
    if [ "$committed" != yes ]; then
        if [ -n "$container" ]; then docker rm -f "$container" >/dev/null 2>&1 || :; fi
        if [ -n "$unit" ]; then
            if [ "$NFQWS_MT_METHOD" = linux ]; then
                if [ "$updating" = yes ]; then systemctl stop nfqws-mtproto.service >/dev/null 2>&1 || :
                else systemctl disable --now nfqws-mtproto.service >/dev/null 2>&1 || :; fi
            elif [ -x "$unit" ]; then "$unit" stop >/dev/null 2>&1 || :; fi
            rm -f "$unit"
            if [ "$NFQWS_MT_METHOD" = linux ]; then systemctl daemon-reload >/dev/null 2>&1 || :; fi
        fi
        if [ -n "$root" ]; then rm -rf "$root"; fi
        if [ -n "$previous_root" ]; then
            mv "$previous_root" "$candidate" || rc=1
        fi
        if [ -n "$previous_unit" ]; then
            mv "$previous_unit" "$service" || rc=1
            if [ "$NFQWS_MT_METHOD" = linux ]; then systemctl daemon-reload || rc=1; fi
        fi
        if [ "$removed_was_enabled" = yes ]; then systemctl enable nfqws-mtproto.service || rc=1; fi
        if [ "$native_transition" = yes ] && [ "$previous_running" = yes ]; then
            if [ "$NFQWS_MT_METHOD" = linux ]; then systemctl start nfqws-mtproto.service || rc=1
            else "$service" start || rc=1; fi
        fi
        if [ -n "$previous_container" ]; then
            docker rename "$previous_container" nfqws-mtproto || rc=1
            if [ "$previous_running" = yes ]; then docker start nfqws-mtproto >/dev/null || rc=1; fi
        fi
    fi
    if [ -n "$work" ]; then rm -rf "$work"; fi
    exit "$rc"
}
trap cleanup 0
trap 'exit 130' INT
trap 'exit 143' HUP TERM

probe=$(cat <<'PY'
@@MTPROTO_READINESS@@
PY
)

if [ "$NFQWS_MT_METHOD" = docker ]; then
    findexe docker >/dev/null || fail 'Docker CLI is missing. Run this on the Docker host.' 'Нет Docker CLI. Выполните команду на устройстве с Docker.'
    docker info >/dev/null 2>&1 || fail 'Docker daemon is unavailable.' 'Служба Docker недоступна.'
    if docker container inspect nfqws-mtproto >/dev/null 2>&1; then
        old_image=$(docker inspect --format '{{.Config.Image}}' nfqws-mtproto)
        old_command=$(docker inspect --format '{{json .Config.Cmd}}' nfqws-mtproto)
        case "$old_image:$old_command" in
            lordarrin/tg-ws-proxy@sha256:*proxy/tg_ws_proxy.py*) ;;
            *) fail 'This container is not our previous MTProto installation; nothing was changed.' 'Этот контейнер не является нашей прежней установкой MTProto; ничего не изменено.';;
        esac
        old_env=$(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' nfqws-mtproto)
        NFQWS_MT_KEY=''
        while IFS= read -r item; do
            case "$item" in
                PROXY_SECRET=*) NFQWS_MT_KEY=${item#*=};;
                PROXY_DC_IPS=*) dc_ips=${item#*=};;
                PROXY_POOL_SIZE=*) pool_size=${item#*=};;
                CFPROXY_DOMAIN=*) cf_domain=${item#*=};;
            esac
        done <<EOF
$old_env
EOF
        NFQWS_MT_PORT=$(docker inspect --format '{{(index (index .HostConfig.PortBindings "1443/tcp") 0).HostPort}}' nfqws-mtproto)
        case "$NFQWS_MT_KEY" in ''|*[!0-9a-fA-F]*) fail 'Invalid existing proxy secret; nothing was changed.' 'Некорректный прежний ключ прокси; ничего не изменено.';; esac
        [ "${#NFQWS_MT_KEY}" = 32 ] || fail 'Invalid existing proxy secret.' 'Некорректный прежний ключ прокси.'
        case "$NFQWS_MT_PORT" in ''|*[!0-9]*) fail 'Cannot read the existing proxy port.' 'Не удалось прочитать прежний порт прокси.';; esac
        [ "$NFQWS_MT_PORT" -ge 1 ] && [ "$NFQWS_MT_PORT" -le 65535 ] || fail 'Invalid existing proxy port.' 'Некорректный прежний порт прокси.'
        if [ "$(docker inspect --format '{{.State.Running}}' nfqws-mtproto)" = true ]; then previous_running=yes; fi
        updating=yes
        refresh_link
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
    fi
    if [ -e "$candidate" ] || [ -L "$candidate" ] || [ -e "$service" ] || [ -L "$service" ]; then
        if [ "${NFQWS_MT_FRESH_ONLY:-no}" = yes ]; then exit 18; fi
        [ -d "$candidate" ] && [ ! -L "$candidate" ] && [ -f "$candidate/config.json" ] && [ -f "$candidate/run.py" ] && [ -f "$service" ] && [ ! -L "$service" ] || fail 'Incomplete previous MTProto installation; nothing was changed.' 'Прежняя установка MTProto неполна; ничего не изменено.'
        grep -F "$candidate/run.py" "$service" >/dev/null && grep -F 'from proxy.tg_ws_proxy import main' "$candidate/run.py" >/dev/null || fail 'These files are not our previous MTProto installation; nothing was changed.' 'Эти файлы не являются нашей прежней установкой MTProto; ничего не изменено.'
        if [ "$NFQWS_MT_METHOD" = entware ]; then
            settings_python=/opt/bin/python3
            if "$service" status >/dev/null 2>&1; then previous_running=yes; fi
        else
            settings_python="$candidate/venv/bin/python"
            [ -x "$settings_python" ] || settings_python=$(findexe python3)
            if systemctl is-active --quiet nfqws-mtproto.service; then previous_running=yes; fi
        fi
        settings=$("$settings_python" - "$candidate/config.json" <<'PY'
import json, re, sys
with open(sys.argv[1]) as f:
    c = json.load(f)
assert type(c['port']) is int and 1024 <= c['port'] <= 65535
assert isinstance(c['secret'], str) and re.fullmatch(r'[0-9a-fA-F]{32}', c['secret'])
print(str(c['port']) + ':' + c['secret'])
PY
)
        NFQWS_MT_PORT=${settings%%:*}
        NFQWS_MT_KEY=${settings#*:}
        updating=yes
        refresh_link
    elif [ "$NFQWS_MT_METHOD" = linux ] && systemctl cat nfqws-mtproto.service >/dev/null 2>&1; then
        fail 'Another MTProto unit exists; nothing was changed.' 'Уже существует другая служба MTProto; ничего не изменено.'
    fi
fi


# An explicit update/removal never installs over an absent or foreign instance.
case "${NFQWS_MT_ACTION:-install}" in
    install) ;;
    update|remove) [ "$updating" = yes ] || fail 'Our previous proxy installation was not found; nothing was changed.' 'Наша прежняя установка прокси не найдена; ничего не изменено.';;
    *) fail 'Unknown proxy action.' 'Неизвестное действие с прокси.';;
esac
if [ "${NFQWS_MT_ACTION:-install}" = remove ]; then
    if [ "$NFQWS_MT_METHOD" = docker ]; then
        old_id=$(docker inspect --format '{{.Id}}' nfqws-mtproto)
        case "$old_id" in ''|*[!0-9a-f]*) fail 'Cannot identify the previous container.' 'Не удалось определить прежний контейнер.';; esac
        old_name="nfqws-mtproto-removed-$old_id"
        docker rename nfqws-mtproto "$old_name"
        previous_container=$old_name
        docker stop "$old_name" >/dev/null
        [ "$(docker inspect --format '{{.State.Running}}' "$old_name")" = false ] || fail 'The proxy is still running.' 'Прокси ещё работает.'
        saved="$old_name"
    else
        saved_root=$(mktemp -d "$candidate.removed.XXXXXX")
        rmdir "$saved_root"
        saved_unit=$(mktemp "$service.removed.XXXXXX")
        native_transition=yes
        if [ "$NFQWS_MT_METHOD" = linux ]; then systemctl stop nfqws-mtproto.service
        else "$service" stop; fi
        if [ "$NFQWS_MT_METHOD" = linux ]; then
            if systemctl is-enabled --quiet nfqws-mtproto.service; then removed_was_enabled=yes; fi
            systemctl disable nfqws-mtproto.service
        fi
        mv "$candidate" "$saved_root"
        previous_root=$saved_root
        mv "$service" "$saved_unit"
        previous_unit=$saved_unit
        if [ "$NFQWS_MT_METHOD" = linux ]; then systemctl daemon-reload; fi
        saved="$saved_root $saved_unit"
    fi
    committed=yes
    msg 'Proxy removed from service. Settings and a stopped backup were retained at:' 'Прокси удалён из запуска. Настройки и остановленная резервная копия сохранены:'
    printf '%s\n' "$saved"
    exit 0
fi

if [ "$NFQWS_MT_METHOD" != docker ]; then
curlbin=$(findexe curl) || fail 'curl is required.' 'Нужна программа curl.'
printf '' | sha256sum >/dev/null 2>&1 || fail 'sha256sum is required.' 'Нужна программа sha256sum.'
work=$(mktemp -d /tmp/nfqws-mtproto.XXXXXX)
msg 'Downloading verified proxy source...' 'Скачивание исходников прокси с проверкой...'
"$curlbin" -fL --connect-timeout 10 --max-time 120 --retry 2 \
    'https://codeload.github.com/Flowseal/tg-ws-proxy/tar.gz/6690b788432fd0f59b0f38e228494bcd6bede1ca' -o "$work/source.tgz"
printf '%s  %s\n' '8e93c7c17074f49ba69f97abae75d196317c215eb278e943d3c5f3b073b4c145' "$work/source.tgz" | sha256sum -c -
mkdir "$work/source"
tar -xzf "$work/source.tgz" -C "$work/source"
source="$work/source/tg-ws-proxy-6690b788432fd0f59b0f38e228494bcd6bede1ca"
fi

if [ "$NFQWS_MT_METHOD" = docker ]; then
    image='@@MTPROTO_DOCKER_IMAGE@@'
    launcher=$(cat <<'SH'
@@MTPROTO_DOCKER_LAUNCHER@@
SH
)
    health=$(cat <<'SH'
@@MTPROTO_HEALTH_COMMAND@@
SH
)
    msg 'Downloading the pinned Docker image...' 'Загрузка закреплённого образа Docker...'
    docker pull "$image"
    if [ "$updating" = yes ]; then
        old_id=$(docker inspect --format '{{.Id}}' nfqws-mtproto)
        case "$old_id" in ''|*[!0-9a-f]*) fail 'Cannot identify the previous container.' 'Не удалось определить прежний контейнер.';; esac
        old_name="nfqws-mtproto-previous-$old_id"
        # Rename first, so a failure while stopping still has a rollback target.
        docker rename nfqws-mtproto "$old_name"
        previous_container=$old_name
        docker stop "$previous_container" >/dev/null
    fi
    container=$(docker create --name nfqws-mtproto --restart unless-stopped \
        --entrypoint /sbin/tini \
        --health-cmd "$health" --health-interval 5m --health-timeout 20s --health-start-period 10s --health-retries 3 \
        --log-opt max-size=5m --log-opt max-file=2 \
        --cap-drop ALL --security-opt no-new-privileges:true \
        -p "$NFQWS_MT_PORT:1443" -e "PROXY_SECRET=$NFQWS_MT_KEY" \
        -e PROXY_HOST=0.0.0.0 -e PROXY_PORT=1443 \
        -e "PROXY_DC_IPS=$dc_ips" \
        -e "PROXY_POOL_SIZE=$pool_size" -e "CFPROXY_DOMAIN=$cf_domain" \
        "$image" -- /bin/sh -c "$launcher")
    docker start "$container" >/dev/null
    sleep 3
    [ "$(docker inspect --format '{{.State.Running}}' "$container")" = true ] || fail 'Proxy stopped. Check Docker logs.' 'Прокси остановился. Проверьте журнал Docker.'
    docker exec "$container" /opt/venv/bin/python -c "$probe" 127.0.0.1 1443 15 || fail 'Telegram did not respond; the new container was rolled back.' 'Telegram не ответил; новый контейнер удалён.'
else
    if [ "$updating" = yes ]; then root=$(mktemp -d "$candidate.new.XXXXXX")
    else mkdir "$candidate"; root=$candidate; fi
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
    NFQWS_MT_CONFIG_KEY="$NFQWS_MT_KEY" "$python" - "$root" "$NFQWS_MT_PORT" "$updating" <<'PY'
import json, os, pwd, socket, sys
root, port, updating = sys.argv[1:]
secret = os.environ['NFQWS_MT_CONFIG_KEY']
assert sys.version_info >= (3, 8), 'Python 3.8+ required'
pwd.getpwnam('nobody')
sys.path[:0] = [root + '/app', root + '/app/vendor']
from proxy._aes import Cipher, algorithms, modes
import httpx, certifi, h2
if updating != 'yes':
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
secret = config['secret']
@@MTPROTO_LOG_REDACTION@@
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
    if [ "$updating" = yes ]; then
        # Prepare everything while the old service is still available.
        saved_root=$(mktemp -d "$candidate.previous.XXXXXX")
        rmdir "$saved_root"
        saved_unit=$(mktemp "$service.previous.XXXXXX")
        native_transition=yes
        if [ "$NFQWS_MT_METHOD" = linux ]; then systemctl stop nfqws-mtproto.service
        else "$service" stop; fi
        mv "$candidate" "$saved_root"
        previous_root=$saved_root
        mv "$service" "$saved_unit"
        previous_unit=$saved_unit
        mv "$root" "$candidate"
        root=$candidate
        if [ "$NFQWS_MT_METHOD" = linux ]; then python="$candidate/venv/bin/python"; fi
    fi
    if [ "$NFQWS_MT_METHOD" = entware ]; then
        # The service only stops the process whose command line matches this runner.
        cat > "$work/service" <<'SH'
#!/bin/sh
root=/opt/share/nfqws-mtproto
pidfile=/opt/var/run/nfqws-mtproto.pid
log=/opt/var/log/nfqws-mtproto.log
PATH=/opt/bin:/opt/sbin:/usr/sbin:/usr/bin:/sbin:/bin
bb=/opt/libexec/nfqws2-asus/busybox
if [ -x /opt/libexec/nfqws2-asus/busybox ]; then
    tr() { /opt/libexec/nfqws2-asus/busybox tr "$@"; }
    grep() { /opt/libexec/nfqws2-asus/busybox grep "$@"; }
else
    bb=/bin/busybox
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
    # Daemonize before exec: the process must outlive the installing SSH session.
    "$bb" start-stop-daemon -S -b -m -p "$pidfile" -x /bin/sh -- -c \
        'exec /opt/bin/python3 "$1/run.py" >> "$2" 2>&1' nfqws-mtproto "$root" "$log" || exit 1
    count=0
    while [ "$count" -lt 50 ]; do
        owned && exit 0
        count=$((count + 1))
        "$bb" sleep 0.1
    done
    echo MTProto_START_FAILED >&2
    exit 1
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
        unit=$service
        (set -C; cat "$work/service" > "$service")
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
ExecStart=$candidate/venv/bin/python $candidate/run.py
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
[Install]
WantedBy=multi-user.target
EOF
        unit=$service
        (set -C; cat "$work/service" > "$service")
        chmod 644 "$unit"
        systemctl daemon-reload
        if [ "$updating" = yes ]; then systemctl start nfqws-mtproto.service
        else systemctl enable --now nfqws-mtproto.service; fi
        sleep 3
        systemctl is-active --quiet nfqws-mtproto.service
    fi
    NFQWS_MT_PROBE_ROOT="$root" NFQWS_MT_PROBE_SECRET="$NFQWS_MT_KEY" \
        "$python" -c "$probe" 127.0.0.1 "$NFQWS_MT_PORT" 15 || {
            msg 'Telegram did not respond; rolling back the installation.' 'Telegram не ответил; выполняется откат установки.' >&2
            exit 19
        }
fi
committed=yes
msg 'Telegram response verified. Add the proxy:' 'Ответ Telegram проверен. Добавьте прокси:'
printf '%s\n' "$NFQWS_MT_LINK"
