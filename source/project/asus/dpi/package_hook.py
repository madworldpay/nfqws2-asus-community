"""Inline the new controller before replacing a package with older hooks."""
from pathlib import Path
import shlex

HERE=Path(__file__).resolve().parent


def shutdown_hook(php, *, runtime='/tmp/nfqws2-dpi-terminal', temporary_parent='/tmp', asus_busybox=False):
    source=(HERE.parents[1]/'webui/web/public/dpi-terminal-lifecycle.php').read_text()
    # Trusted build/test dependencies only; neither value comes from HTTP.
    literal="'"+runtime.replace('\\','\\\\').replace("'","\\'")+"'"
    boundary="$this->root=$root??'/tmp/nfqws2-dpi-terminal';"
    if source.count(boundary)!=1:raise RuntimeError('Detector shutdown root contract changed')
    source=source.replace(boundary,'$this->root=$root??'+literal+';',1)
    quote=shlex.quote
    tool='"$ASUS_MIGRATION_BUSYBOX" ' if asus_busybox else ''
    return ('''# Stop an old interactive Detector before unpacking replaces its helper.
if [ -z "$IPKG_INSTROOT" ] && { [ -e RUNTIME ] || [ -L RUNTIME ]; }; then
(
    set -e
    umask 077
    dpi_stop_dir=$(TOOLmktemp -d TEMPLATE) || exit 1
    trap 'TOOLrm -f "$dpi_stop_dir/stop.php"; TOOLrmdir "$dpi_stop_dir"' 0
    TOOLcat > "$dpi_stop_dir/stop.php" <<'NFQWS_DPI_STOP_PHP' || exit 1
'''.replace('RUNTIME',quote(runtime)).replace('TEMPLATE',quote(temporary_parent+'/.nfqws-dpi-stop.XXXXXX')).replace('TOOL',tool)+source+'''
NFQWS_DPI_STOP_PHP
    PHP -n -d register_argc_argv=1 -q -f "$dpi_stop_dir/stop.php" -- stop
) || exit 1
fi
'''.replace('PHP -n',quote(str(php))+' -n')).encode()
