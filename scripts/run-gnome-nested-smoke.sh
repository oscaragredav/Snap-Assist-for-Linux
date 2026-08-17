#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
for command_name in dbus-run-session gnome-shell gsettings gdbus glib-compile-schemas timeout; do
    command -v "${command_name}" >/dev/null 2>&1 || {
        echo "SKIP: falta ${command_name} para GNOME anidado." >&2
        exit 77
    }
done

temporary="$(mktemp -d /tmp/snapassist-gnome-nested.XXXXXX)"
cleanup() {
    [[ "${temporary}" == /tmp/snapassist-gnome-nested.* ]] || return
    for _attempt in $(seq 1 50); do
        if command -v mountpoint >/dev/null 2>&1 && \
           mountpoint -q "${runtime_dir:-${temporary}/runtime}/doc"; then
            if command -v fusermount3 >/dev/null 2>&1; then
                fusermount3 -u "${runtime_dir:-${temporary}/runtime}/doc" || true
            elif command -v fusermount >/dev/null 2>&1; then
                fusermount -u "${runtime_dir:-${temporary}/runtime}/doc" || true
            fi
        fi
        rm -rf -- "${temporary}" 2>/dev/null || true
        [[ ! -e "${temporary}" ]] && return 0
        sleep 0.1
    done
    echo "Error: quedaron residuos del smoke en ${temporary}." >&2
    return 1
}
trap cleanup EXIT

runtime_dir="${temporary}/runtime"
home_dir="${temporary}/home"
config_dir="${temporary}/config"
extension_dir="${home_dir}/.local/share/gnome-shell/extensions/snapassist-test@oscaragredav"
install -d -m 0700 "${runtime_dir}" "${home_dir}" "${config_dir}" "${extension_dir}"
cp -a "${ROOT_DIR}/gnome-extension/." "${extension_dir}/"
glib-compile-schemas --strict "${extension_dir}/schemas"

export HOME="${home_dir}"
export XDG_CONFIG_HOME="${config_dir}"
export XDG_DATA_HOME="${home_dir}/.local/share"
export XDG_RUNTIME_DIR="${runtime_dir}"
export GSETTINGS_BACKEND=keyfile
export SNAPASSIST_NESTED_LOG="${temporary}/gnome-shell.log"

session_stdout="${temporary}/session.stdout"
session_stderr="${temporary}/session.stderr"
if ! timeout --signal=TERM --kill-after=5s 25s \
    dbus-run-session -- bash "${ROOT_DIR}/scripts/gnome-nested-session.sh" \
    >"${session_stdout}" 2>"${session_stderr}"; then
    cat "${session_stdout}"
    cat "${session_stderr}" >&2
    exit 1
fi
grep -E '^\{"healthy"' "${session_stdout}"
