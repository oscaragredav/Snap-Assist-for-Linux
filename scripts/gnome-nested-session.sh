#!/usr/bin/env bash
set -euo pipefail

UUID="snapassist-test@oscaragredav"
BUS_NAME="org.snapassist.Shell.Test"
OBJECT_PATH="/org/snapassist/Shell/Test"
INTERFACE="org.snapassist.Shell1"
LOG_FILE="${SNAPASSIST_NESTED_LOG:?falta SNAPASSIST_NESTED_LOG}"

gsettings set org.gnome.shell disable-user-extensions false
gsettings set org.gnome.shell enabled-extensions "['${UUID}']"

gnome-shell \
    --headless \
    --wayland \
    --no-x11 \
    --virtual-monitor 1280x720 \
    --wayland-display snapassist-ci-0 \
    >"${LOG_FILE}" 2>&1 &
shell_pid=$!

cleanup() {
    if kill -0 "${shell_pid}" 2>/dev/null; then
        kill "${shell_pid}" 2>/dev/null || true
        wait "${shell_pid}" 2>/dev/null || true
    fi
}
trap cleanup EXIT

has_owner() {
    gdbus call --session \
        --dest org.freedesktop.DBus \
        --object-path /org/freedesktop/DBus \
        --method org.freedesktop.DBus.NameHasOwner "${BUS_NAME}" \
        2>/dev/null | grep -q true
}

wait_for_owner() {
    local expected="$1"
    for _attempt in $(seq 1 100); do
        if ! kill -0 "${shell_pid}" 2>/dev/null; then
            echo "GNOME Shell terminó antes del handshake." >&2
            tail -80 "${LOG_FILE}" >&2
            return 1
        fi
        if has_owner; then
            [[ "${expected}" == "present" ]] && return 0
        else
            [[ "${expected}" == "absent" ]] && return 0
        fi
        sleep 0.1
    done
    echo "Timeout esperando bus ${BUS_NAME}: ${expected}." >&2
    tail -80 "${LOG_FILE}" >&2
    return 1
}

wait_for_owner present
protocol_result="$(gdbus call --session --dest "${BUS_NAME}" \
    --object-path "${OBJECT_PATH}" --method "${INTERFACE}.GetProtocolInfo")"
snapshot_result="$(gdbus call --session --dest "${BUS_NAME}" \
    --object-path "${OBJECT_PATH}" --method "${INTERFACE}.GetSnapshot")"
shortcut_result="$(gdbus call --session --dest "${BUS_NAME}" \
    --object-path "${OBJECT_PATH}" --method "${INTERFACE}.ConfigureShortcuts" \
    nested-shortcuts '{"layout_menu":"super+z","snap_groups":"super+alt+tab","help":"super+f2"}')"
layout_result="$(gdbus call --session --dest "${BUS_NAME}" \
    --object-path "${OBJECT_PATH}" --method "${INTERFACE}.ShowLayouts" \
    nested-layouts 7 '{"title":"QA","layouts":[{"name":"1","zones":[{"x":0,"y":0,"w":1,"h":1}]},{"name":"2","zones":[{"x":0,"y":0,"w":1,"h":1}]},{"name":"3","zones":[{"x":0,"y":0,"w":1,"h":1}]},{"name":"4","zones":[{"x":0,"y":0,"w":1,"h":1}]},{"name":"5","zones":[{"x":0,"y":0,"w":1,"h":1}]},{"name":"6","zones":[{"x":0,"y":0,"w":1,"h":1}]},{"name":"7","zones":[{"x":0,"y":0,"w":1,"h":1}]}]}')"
hide_result="$(gdbus call --session --dest "${BUS_NAME}" \
    --object-path "${OBJECT_PATH}" --method "${INTERFACE}.HidePresentation" \
    nested-hide 7)"
GSETTINGS_SCHEMA_DIR="${HOME}/.local/share/gnome-shell/extensions/${UUID}/schemas" \
    gsettings get org.snapassist.shell.test show-help | grep -q "<Super>F2"

SNAPASSIST_PROTOCOL_RESULT="${protocol_result}" \
SNAPASSIST_SNAPSHOT_RESULT="${snapshot_result}" \
SNAPASSIST_SHORTCUT_RESULT="${shortcut_result}" \
SNAPASSIST_LAYOUT_RESULT="${layout_result}" \
SNAPASSIST_HIDE_RESULT="${hide_result}" \
/usr/bin/python3 -c 'import ast, json, os; unpack=lambda key: json.loads(ast.literal_eval(os.environ[key])[0]); protocol=unpack("SNAPASSIST_PROTOCOL_RESULT"); snapshot=unpack("SNAPASSIST_SNAPSHOT_RESULT"); shortcuts=unpack("SNAPASSIST_SHORTCUT_RESULT"); layouts=unpack("SNAPASSIST_LAYOUT_RESULT"); hidden=unpack("SNAPASSIST_HIDE_RESULT"); assert protocol["protocolVersion"] == 1; assert protocol["interfaceName"] == "org.snapassist.Shell1"; assert snapshot["sessionId"] == protocol["sessionId"]; assert snapshot["sequence"] >= 1; assert len(snapshot["monitors"]) == 1; assert snapshot["monitors"][0]["geometry"]["width"] == 1280; assert shortcuts["accepted"] and layouts["accepted"] and hidden["accepted"]; print(json.dumps({"healthy": True, "protocolVersion": protocol["protocolVersion"], "sessionId": protocol["sessionId"], "snapshotSequence": snapshot["sequence"], "monitors": len(snapshot["monitors"]), "shortcuts": True, "layouts": True}, sort_keys=True))'

# Simula el ciclo de bloqueo/desbloqueo: GNOME retira las extensiones de
# usuario y después vuelve a cargarlas con un objeto D-Bus nuevo.
gsettings set org.gnome.shell enabled-extensions "[]"
wait_for_owner absent
gsettings set org.gnome.shell enabled-extensions "['${UUID}']"
wait_for_owner present
reconnected_protocol="$(gdbus call --session --dest "${BUS_NAME}" \
    --object-path "${OBJECT_PATH}" --method "${INTERFACE}.GetProtocolInfo")"
reconnected_snapshot="$(gdbus call --session --dest "${BUS_NAME}" \
    --object-path "${OBJECT_PATH}" --method "${INTERFACE}.GetSnapshot")"
SNAPASSIST_PROTOCOL_RESULT="${reconnected_protocol}" \
SNAPASSIST_SNAPSHOT_RESULT="${reconnected_snapshot}" \
/usr/bin/python3 -c 'import ast, json, os; unpack=lambda key: json.loads(ast.literal_eval(os.environ[key])[0]); protocol=unpack("SNAPASSIST_PROTOCOL_RESULT"); snapshot=unpack("SNAPASSIST_SNAPSHOT_RESULT"); assert snapshot["sessionId"] == protocol["sessionId"]; assert snapshot["sequence"] >= 1'

gsettings set org.gnome.shell enabled-extensions "[]"
wait_for_owner absent

if grep -E "JS ERROR|Extension .* had error|snapassist.*ERROR" "${LOG_FILE}"; then
    echo "La extensión registró un error en GNOME anidado." >&2
    exit 1
fi
