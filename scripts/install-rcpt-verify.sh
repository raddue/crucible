#!/bin/sh
# Requires POSIX sh and GNU coreutils (stat -c, install, readlink -f, mktemp).
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
# if overriding the install dir, set the same path in shared/return-convention.md
# and the installer documentation. Overrides must be absolute, shell-safe paths.
set -eu

TARGET="${CRUCIBLE_RCPT_INSTALL_DIR:-/usr/local/libexec/crucible}"
PY="${PYTHON:-/usr/bin/python3}"
case "$TARGET" in /*) ;; *) echo "install dir must be absolute: $TARGET" >&2; exit 1 ;; esac
case "$PY" in /*) ;; *) echo "python path must be absolute: $PY" >&2; exit 1 ;; esac
case "$TARGET$PY" in *[!A-Za-z0-9_./-]*) echo "paths may contain only letters, digits, _, ., /, and -" >&2; exit 1 ;; esac
case "$TARGET" in /usr/local/libexec/crucible) ;; *) echo "NOTE: update skills/shared/return-convention.md and all consumer references to use this CRUCIBLE_RCPT_INSTALL_DIR override: $TARGET" >&2 ;; esac
SRC="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/rcpt_verify.py"

if [ "$(id -u)" -ne 0 ]; then
    echo "target $TARGET must be root-owned (the review-target uid must not be able to write it):" >&2
    echo "  sudo $0" >&2
    exit 1
fi

[ -f "$SRC" ] || { echo "verifier not found: $SRC" >&2; exit 1; }

check_ancestors() {
    label=$1
    parent=$(dirname -- "$2")
    while :; do
        [ -d "$parent" ] && [ ! -L "$parent" ] || {
            echo "$label ancestor must be a real directory: $parent" >&2
        [ "$label" != target ] || echo "Create it first: sudo install -d -o root -g root -m 0755 \"$parent\"" >&2
            exit 1
        }
        owner_mode=$(stat -c '%u:%a' "$parent")
        owner=${owner_mode%%:*}
        mode=${owner_mode#*:}
        [ "$owner" = 0 ] && [ $((0$mode & 022)) -eq 0 ] || {
            echo "$label ancestor must be root-owned and not group/world-writable: $parent" >&2
            [ "$label" != target ] || echo "Create it first: sudo install -d -o root -g root -m 0755 \"$parent\"" >&2
            exit 1
        }
        [ "$parent" = / ] && break
        parent=$(dirname -- "$parent")
    done
}
check_ancestors target "$TARGET"
TARGET_PARENT=$(dirname -- "$TARGET")
if [ ! -d "$TARGET_PARENT" ]; then
    echo "target parent does not exist: $TARGET_PARENT" >&2
    echo "Create it first: sudo install -d -o root -g root -m 0755 \"$TARGET_PARENT\"" >&2
    exit 1
fi
check_ancestors python "$PY"
# The system python path can be a symlink; validate its resolved destination too.
PY=$(readlink -f -- "$PY")
[ -n "$PY" ] && [ -f "$PY" ] && [ -x "$PY" ] && [ ! -L "$PY" ] || {
    echo "python must resolve to an executable regular file" >&2
    exit 1
}
case "$PY" in *[!A-Za-z0-9_./-]*) echo "resolved python path has unsafe characters: $PY" >&2; exit 1 ;; esac
check_ancestors python "$PY"
owner_mode=$(stat -c '%u:%a' "$PY")
owner=${owner_mode%%:*}
mode=${owner_mode#*:}
[ "$owner" = 0 ] && [ $((0$mode & 022)) -eq 0 ] || {
    echo "python must be root-owned and not group/world-writable: $PY" >&2
    exit 1
}

if [ -e "$TARGET" ] || [ -L "$TARGET" ]; then
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
# Stage both files before replacing live paths; do not leave partial writes.
tmp_src=$(mktemp "$TARGET/.rcpt_verify.py.XXXXXX")
tmp_wrapper=$(mktemp "$TARGET/.rcpt-verify.XXXXXX")
trap 'rm -f -- "$tmp_src" "$tmp_wrapper"' EXIT HUP INT TERM
install -o root -g root -m 0755 "$SRC" "$tmp_src"
printf '%s\n' \
    '#!/bin/sh' \
    "exec '$PY' -I '$TARGET/rcpt_verify.py' \"\$@\"" \
    > "$tmp_wrapper"
chown root:root "$tmp_wrapper"
chmod 0755 "$tmp_wrapper"
mv -f -- "$tmp_src" "$TARGET/rcpt_verify.py"
mv -f -- "$tmp_wrapper" "$TARGET/rcpt-verify"
trap - EXIT HUP INT TERM

echo "installed verifier: $TARGET/rcpt_verify.py"
echo "wrapper:            $TARGET/rcpt-verify"
echo
echo "Mandated lint invocation (receipt on stdin, the '-' positional):"
echo "  $TARGET/rcpt-verify --tier2 --strict --root <dispatch-root> --root <findings-root> --ledger <dispatch-root>/receipt-ledger.jsonl -"
echo "Set CRUCIBLE_RCPT_INSTALL_DIR in the consuming convention if this target differs from its documented default."