#!/bin/sh
# All firewall commands and sleeps are mocked; no root or network needed.
set -e
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
CONFFILE="$work/config"
: > "$CONFFILE"
. "$repo/etc/init.d/common"
ISP_INTERFACE='eth0 eth1'
TCP_PORTS=80,443
UDP_PORTS=443
NFQUEUE_NUM=300

mock_iptables() {
  count=$((count + 1))
  printf '%s\n' "$*" >> "$work/commands"
  [ "$count" -ne "$fail_at" ] || return 1
  # Existing chains and missing jumps are normal, handled by -F and -A.
  case " $* " in *' -N '*|*' -C '*) return 1 ;; esac
  return 0
}
iptables() { mock_iptables "$@"; }
ip6tables() { mock_iptables "$@"; }
for cmd in iptables ip6tables; do
  for POLICY_MARK in '' 0x1/0xff; do
    for POLICY_EXCLUDE in 0 1; do
      count=0 fail_at=0
      : > "$work/commands"
      _firewall_start "$cmd" || { echo "Baseline failed" >&2; exit 1; }
      cp "$work/commands" "$work/baseline"
      index=0
      while IFS= read -r args; do
        index=$((index + 1))
        case " $args " in *' -N '*|*' -C '*) continue ;; esac
        count=0 fail_at=$index
        : > "$work/commands"
        if _firewall_start "$cmd"; then
          echo "Lost error from $cmd $args" >&2
          exit 1
        fi
        # Remaining rules/interfaces must still be attempted.
        cmp "$work/commands" "$work/baseline"
      done < "$work/baseline"
    done
  done
done

printf '%s\n' "$$" > "$work/pid"
sed -e "s|/opt/var/run/nfqws2.pid|$work/pid|" \
    -e 's|/opt/etc/init.d/S51nfqws2|fake_apply|' \
    "$repo/etc/ndm/netfilter.d/100-nfqws2.sh" > "$work/hook"
fake_apply() {
  printf '%s\n' "$*" >> "$work/attempts"
  n=$(wc -l < "$work/attempts")
  [ "$n" -gt "$failures" ] && return 0
  return 7
}
sleep() { echo "$*" >> "$work/sleeps"; }
for failures in 0 2 5; do
  : > "$work/attempts"
  : > "$work/sleeps"
  rc=0
  # Production entrypoint does not use errexit.
  (set +e; table=mangle; type=iptables; . "$work/hook") || rc=$?
  if [ "$failures" -eq 5 ]; then
    test "$rc" -eq 7
    attempts=5 pauses=4
  else
    test "$rc" -eq 0
    attempts=$((failures + 1)) pauses=$failures
  fi
  test "$(wc -l < "$work/attempts")" -eq "$attempts"
  test "$(wc -l < "$work/sleeps")" -eq "$pauses"
done
: > "$work/attempts"
(set +e; table=filter; type=iptables; . "$work/hook")
test ! -s "$work/attempts"
rm "$work/pid"
(set +e; table=mangle; type=iptables; . "$work/hook")
test ! -s "$work/attempts"
echo 'Firewall error propagation and retry checks passed'
