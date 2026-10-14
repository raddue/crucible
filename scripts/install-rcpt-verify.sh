#!/bin/sh
# Install rcpt_verify.py to a non-subagent-writable location and emit the pinned,
# isolated invocation wrapper. This is the separate-uid/write-boundary for the
# receipt linter: the review-target (subagent) uid runs non-root, so a root-owned
# install dir and the pinned system interpreter are outside its write reach, and
# `-I` (isolated mode) removes PYTHONPATH/PYTHONSTARTUP/sitecustomize/.pth/site
# from the import surface. Together they close the sys.path[0] stdlib-shadowing
# that a sibling file planted in a worktree `scripts/` exploits (see design doc
# §6.1c "the verifier is a store").
#
# Run ONCE per host, by the operator, as root:  sudo scripts/install-rcpt-verify.sh
# Override the install dir or interpreter via CRUCIBLE_RCPT_INSTALL_DIR / PYTHON;
# overrides must be absolute, shell-safe paths.
set -eu

TARGET="${CRUCIBLE_RCPT_INSTALL_DIR:-/usr/local/libexec/crucible}"
PY="${PYTHON:-/usr/bin/python3}"
case "$TARGET" in /*) ;; *) echo "install dir must be absolute: $TARGET" >&2; exit 1 ;; esac
case "$PY" in /*) ;; *) echo "python path must be absolute: $PY" >&2; exit 1 ;; esac
case "$TARGET$PY" in *[!A-Za-z0-9_./-]*) echo "paths may contain only letters, digits, _, ., /, and -" >&2; exit 1 ;; esac
SRC="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/rcpt_verify.py"

if [ "$(id -u)" -ne 0 ]; then
    echo "target $TARGET must be root-owned (the review-target uid must not be able to write it):" >&2
    echo "  sudo $0" >&2
    exit 1
fi

[ -f "$SRC" ] || { echo "verifier not found: $SRC" >&2; exit 1; }

parent=$(dirname -- "$TARGET")
while :; do
    [ -d "$parent" ] && [ ! -L "$parent" ] || {
        echo "target ancestor must be a real directory: $parent" >&2
        exit 1
    }
    owner_mode=$(stat -c '%u:%a' "$parent")
    owner=${owner_mode%%:*}
    mode=${owner_mode#*:}
    [ "$owner" = 0 ] && [ $((0$mode & 022)) -eq 0 ] || {
        echo "target ancestor must be root-owned and not group/world-writable: $parent" >&2
        exit 1
    }
    [ "$parent" = / ] && break
    parent=$(dirname -- "$parent")
done

if [ -e "$TARGET" ]; then
    [ -d "$TARGET" ] && [ ! -L "$TARGET" ] || {
        echo "target must be a real directory: $TARGET" >&2
        exit 1
    }
    [ "$(stat -c '%u:%a' "$TARGET")" = 0:755 ] || {
        echo "target must be root-owned with mode 755: $TARGET" >&2
        exit 1
    }
else
    install -d -o root -g root -m 0755 "$TARGET"
fi
install -o root -g root -m 0755 "$SRC" "$TARGET/rcpt_verify.py"

printf '%s\n' \
    '#!/bin/sh' \
    "exec '$PY' -I '$TARGET/rcpt_verify.py' \"\$@\"" \
    > "$TARGET/rcpt-verify"
chown root:root "$TARGET/rcpt-verify"
chmod 0755 "$TARGET/rcpt-verify"

( cd "$TARGET" && sha256sum "rcpt_verify.py" ) > "$TARGET/rcpt_verify.sha256"

echo "installed verifier: $TARGET/rcpt_verify.py"
echo "wrapper:            $TARGET/rcpt-verify"
echo "sha256:             $(cat "$TARGET/rcpt_verify.sha256")"
echo
echo "Mandated lint invocation (receipt on stdin, the '-' positional):"
echo "  $TARGET/rcpt-verify --tier2 --strict --root <dispatch-root> --root <findings-root> --ledger <dispatch-root>/receipt-ledger.jsonl -"