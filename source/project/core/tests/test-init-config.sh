#!/bin/sh
# Run with sh, dash, or busybox ash.
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
CONFFILE="$work/config"
: > "$CONFFILE"
. "$repo/etc/init.d/common"

reset_args() {
  NFQWS_BASE_ARGS=
  NFQWS_ARGS=
  NFQWS_ARGS_QUIC=
  NFQWS_ARGS_UDP=
  NFQWS_EXTRA_ARGS=
  NFQWS_ARGS_IPSET=
}
reset_args
validate_config
NFQWS_ARGS='--filter-tcp=443
--lua-desync=fake:blob=0x00000000'
validate_config

for name in NFQWS_BASE_ARGS NFQWS_ARGS NFQWS_ARGS_QUIC NFQWS_ARGS_UDP NFQWS_EXTRA_ARGS NFQWS_ARGS_IPSET; do
  reset_args
  # Names come only from the fixed list above.
  eval "$name='--filter-tcp=443
--new'"
  if validate_config > "$work/output" 2> "$work/error"; then
    echo "Accepted forbidden --new in $name" >&2
    exit 1
  fi
  grep -q "Using --new in $name is not allowed" "$work/output"
  test ! -s "$work/error"
done
reset_args
NFQWS_ARGS_CUSTOM='--filter-tcp=80 --new --filter-tcp=443'
validate_config
printf '%s\n' 'Config validation checks passed'
