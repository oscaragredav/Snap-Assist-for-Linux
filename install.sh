#!/usr/bin/env bash
set -euo pipefail

# Instalador idempotente de SnapAssist para el usuario actual.
# Las variables SNAPASSIST_* permiten probarlo en un árbol temporal sin tocar
# el home real; no son necesarias durante una instalación normal.
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CHANNEL="stable"
PROMOTE=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --channel)
            [[ $# -ge 2 ]] || break
            CHANNEL="$2"
            shift 2
            ;;
        --promote)
            PROMOTE=1
            shift
            ;;
        *) break ;;
    esac
done
if [[ $# -ne 0 || ( "${CHANNEL}" != "stable" && "${CHANNEL}" != "test" ) ]]; then
    echo "Uso: bash install.sh [--channel stable|test] [--promote]" >&2
    exit 2
fi

DATA_HOME="${SNAPASSIST_DATA_HOME:-${XDG_DATA_HOME:-${HOME}/.local/share}}"
CONFIG_HOME="${SNAPASSIST_CONFIG_HOME:-${XDG_CONFIG_HOME:-${HOME}/.config}}"
BIN_HOME="${SNAPASSIST_BIN_HOME:-${HOME}/.local/bin}"
UNIT_DIR="${CONFIG_HOME}/systemd/user"
if [[ "${CHANNEL}" == "stable" ]]; then
    INSTANCE_NAME="snapassist"
    OTHER_INSTANCE="snapassist-test"
else
    INSTANCE_NAME="snapassist-test"
    OTHER_INSTANCE="snapassist"
fi
INSTALL_DIR="${DATA_HOME}/${INSTANCE_NAME}"
APP_CONFIG_DIR="${CONFIG_HOME}/${INSTANCE_NAME}"
ENV_FILE="${APP_CONFIG_DIR}/environment"
SETTINGS_FILE="${APP_CONFIG_DIR}/settings.json"
LOG_DIR="${INSTALL_DIR}/logs"
BACKUP_BASE="${DATA_HOME}/snapassist-backups/${INSTANCE_NAME}"
UNIT_NAME="${INSTANCE_NAME}.service"
OTHER_UNIT="${OTHER_INSTANCE}.service"
PYTHON_BIN="${SNAPASSIST_PYTHON:-python3}"
RUNTIME="${SNAPASSIST_RUNTIME:-x11}"
if [[ -z "${SNAPASSIST_RUNTIME:-}" && "${CHANNEL}" == "test" && "${SNAPASSIST_SKIP_SYSTEMD:-0}" != "1" ]]; then
    desktop="${XDG_CURRENT_DESKTOP:-}"
    if [[ "${XDG_SESSION_TYPE:-}" == "wayland" || "${desktop,,}" == *gnome* ]]; then
        RUNTIME="gnome"
    fi
fi
if [[ "${RUNTIME}" != "x11" && "${RUNTIME}" != "gnome" ]]; then
    echo "Error: SNAPASSIST_RUNTIME debe ser x11 o gnome." >&2
    exit 2
fi
command -v "${PYTHON_BIN}" >/dev/null 2>&1 || {
    echo "Error: no se encontró ${PYTHON_BIN}. Instala Python 3.11 o superior." >&2
    exit 1
}

"${PYTHON_BIN}" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' || {
    echo "Error: SnapAssist requiere Python 3.11 o superior." >&2
    exit 1
}

version="$("${PYTHON_BIN}" -c 'from pathlib import Path; import re, sys; text=(Path(sys.argv[1]) / "snapassist/__init__.py").read_text(); print(re.search(r"__version__\s*=\s*[\"'\''\"]([^\"'\''\"]+)", text).group(1))' "${SOURCE_DIR}" 2>/dev/null || printf 'unknown')"
if [[ "${CHANNEL}" == "stable" && "${version}" =~ (dev|a|b|rc) && ${PROMOTE} -ne 1 ]]; then
    echo "Error: ${version} es una versión de desarrollo; no se sobrescribirá stable." >&2
    echo "Instálala con --channel test. Usa --promote solo tras aprobar U7/U8." >&2
    exit 1
fi
if [[ -z "${SNAPASSIST_RUNTIME:-}" && "${CHANNEL}" == "stable" && "${version}" == 2.* && "${SNAPASSIST_SKIP_SYSTEMD:-0}" != "1" ]]; then
    desktop="${XDG_CURRENT_DESKTOP:-}"
    if [[ "${XDG_SESSION_TYPE:-}" == "wayland" || "${desktop,,}" == *gnome* ]]; then
        RUNTIME="gnome"
    fi
fi
if [[ "${CHANNEL}" == "stable" && "${RUNTIME}" == "gnome" && "${version}" != 2.* ]]; then
    echo "Error: el baseline estable anterior a 2.0 solo admite X11." >&2
    exit 2
fi

if [[ "${RUNTIME}" == "x11" ]] && ! "${PYTHON_BIN}" -c 'import tkinter' >/dev/null 2>&1; then
    echo "Error: falta tkinter. En Zorin/Ubuntu instala python3-tk." >&2
    exit 1
fi

if [[ "${RUNTIME}" == "gnome" ]] && ! /usr/bin/python3 -c 'import dbus; from gi.repository import GLib' >/dev/null 2>&1; then
    echo "Error: el runtime GNOME requiere python3-dbus y python3-gi del sistema." >&2
    exit 1
fi

if [[ "${SNAPASSIST_SKIP_SYSTEMD:-0}" != "1" ]]; then
    if [[ "${RUNTIME}" == "x11" && "${XDG_SESSION_TYPE:-x11}" != "x11" ]]; then
        echo "Error: SnapAssist todavía requiere una sesión X11 (sesión actual: ${XDG_SESSION_TYPE:-desconocida})." >&2
        echo "Cierra sesión, selecciona una sesión con Xorg/X11 en la pantalla de acceso y vuelve a intentarlo." >&2
        exit 1
    fi
    if [[ -z "${DISPLAY:-}" ]]; then
        echo "Error: DISPLAY no está definido. Ejecuta install.sh desde una terminal abierta dentro de tu sesión X11." >&2
        exit 1
    fi
fi

install -d "${UNIT_DIR}" "${APP_CONFIG_DIR}" "${BIN_HOME}" "${BACKUP_BASE}"
if [[ -d "${INSTALL_DIR}/snapassist" ]]; then
    backup_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
    backup_dir="${BACKUP_BASE}/${backup_id}"
    install -d "${backup_dir}/payload"
    cp -a "${INSTALL_DIR}/snapassist" "${backup_dir}/payload/"
    for backup_file in requirements.txt README.md LICENSE CHANGELOG.md pyproject.toml install-manifest; do
        if [[ -f "${INSTALL_DIR}/${backup_file}" ]]; then
            cp -a "${INSTALL_DIR}/${backup_file}" "${backup_dir}/payload/"
        fi
    done
    if [[ -f "${UNIT_DIR}/${UNIT_NAME}" ]]; then
        cp -a "${UNIT_DIR}/${UNIT_NAME}" "${backup_dir}/${UNIT_NAME}"
    fi
fi
install -d "${INSTALL_DIR}" "${LOG_DIR}"
cp -a "${SOURCE_DIR}/snapassist" "${INSTALL_DIR}/"
install -m 0644 "${SOURCE_DIR}/requirements.txt" "${INSTALL_DIR}/requirements.txt"
install -m 0644 "${SOURCE_DIR}/README.md" "${INSTALL_DIR}/README.md"
install -m 0644 "${SOURCE_DIR}/LICENSE" "${INSTALL_DIR}/LICENSE"
install -m 0644 "${SOURCE_DIR}/CHANGELOG.md" "${INSTALL_DIR}/CHANGELOG.md"
install -m 0644 "${SOURCE_DIR}/pyproject.toml" "${INSTALL_DIR}/pyproject.toml"
unit_template="$(<"${SOURCE_DIR}/snapassist.service")"
unit_template="${unit_template//@INSTALL_DIR@/${INSTALL_DIR}}"
unit_template="${unit_template//@ENV_FILE@/${ENV_FILE}}"
unit_template="${unit_template//@CONFLICT_UNIT@/${OTHER_UNIT}}"
unit_template="${unit_template//@CHANNEL@/${CHANNEL}}"
unit_template="${unit_template//@LOG_DIR@/${LOG_DIR}}"
unit_template="${unit_template//@SETTINGS_FILE@/${SETTINGS_FILE}}"
if [[ "${RUNTIME}" == "gnome" ]]; then
    EXEC_START_PRE=""
    EXEC_START="/usr/bin/python3 -m snapassist.gnome_main"
else
    EXEC_START_PRE="ExecStartPre=\"${INSTALL_DIR}/venv/bin/python\" -m snapassist.wait_for_x11"
    EXEC_START="\"${INSTALL_DIR}/venv/bin/python\" -m snapassist.main"
fi
unit_template="${unit_template//@EXEC_START_PRE@/${EXEC_START_PRE}}"
unit_template="${unit_template//@EXEC_START@/${EXEC_START}}"
printf '%s\n' "${unit_template}" >"${UNIT_DIR}/${UNIT_NAME}"
install -m 0755 "${SOURCE_DIR}/snapassist-channel" "${BIN_HOME}/snapassist-channel"
install -m 0755 "${SOURCE_DIR}/snapassist-manage" "${BIN_HOME}/snapassist-manage"

EXTENSION_UUID=""
if [[ ( "${CHANNEL}" == "test" || "${RUNTIME}" == "gnome" ) && -d "${SOURCE_DIR}/gnome-extension" ]]; then
    if [[ "${CHANNEL}" == "test" ]]; then
        EXTENSION_UUID="snapassist-test@oscaragredav"
    else
        EXTENSION_UUID="snapassist@oscaragredav"
    fi
    EXTENSION_DIR="${DATA_HOME}/gnome-shell/extensions/${EXTENSION_UUID}"
    install -d "${EXTENSION_DIR}"
    cp -a "${SOURCE_DIR}/gnome-extension/." "${EXTENSION_DIR}/"
    install -d "${EXTENSION_DIR}/protocol"
    install -m 0644 \
        "${SOURCE_DIR}/protocol/org.snapassist.Shell1.xml" \
        "${EXTENSION_DIR}/protocol/org.snapassist.Shell1.xml"
    if [[ "${CHANNEL}" == "stable" ]]; then
        "${PYTHON_BIN}" -c 'import json, pathlib, sys; path=pathlib.Path(sys.argv[1]); value=json.loads(path.read_text()); value.update({"uuid":"snapassist@oscaragredav","name":"SnapAssist","description":"SnapAssist native integration for GNOME Shell 46","settings-schema":"org.snapassist.shell","snapassist-channel":"stable","version":20000}); path.write_text(json.dumps(value, indent=2) + "\n")' "${EXTENSION_DIR}/metadata.json"
        cp "${EXTENSION_DIR}/schemas/org.snapassist.shell.test.gschema.xml" \
            "${EXTENSION_DIR}/schemas/org.snapassist.shell.gschema.xml"
        sed -i \
            -e 's/org\.snapassist\.shell\.test/org.snapassist.shell/g' \
            -e 's#/org/snapassist/shell/test/#/org/snapassist/shell/#g' \
            "${EXTENSION_DIR}/schemas/org.snapassist.shell.gschema.xml"
        rm "${EXTENSION_DIR}/schemas/org.snapassist.shell.test.gschema.xml"
    fi
    if command -v glib-compile-schemas >/dev/null 2>&1; then
        glib-compile-schemas --strict "${EXTENSION_DIR}/schemas"
    fi
fi

commit="$(git -C "${SOURCE_DIR}" rev-parse --verify HEAD 2>/dev/null || printf 'unknown')"
source_dirty="unknown"
if git -C "${SOURCE_DIR}" diff --quiet --ignore-submodules HEAD 2>/dev/null && \
   [[ -z "$(git -C "${SOURCE_DIR}" ls-files --others --exclude-standard 2>/dev/null)" ]]; then
    source_dirty="false"
elif git -C "${SOURCE_DIR}" rev-parse --verify HEAD >/dev/null 2>&1; then
    source_dirty="true"
fi
{
    printf 'channel=%s\n' "${CHANNEL}"
    printf 'version=%s\n' "${version}"
    printf 'commit=%s\n' "${commit}"
    printf 'source_dirty=%s\n' "${source_dirty}"
    printf 'installed_at_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'service=%s\n' "${UNIT_NAME}"
    printf 'runtime=%s\n' "${RUNTIME}"
    printf 'install_dir=%s\n' "${INSTALL_DIR}"
    if [[ -n "${EXTENSION_UUID}" ]]; then
        printf 'extension_uuid=%s\n' "${EXTENSION_UUID}"
    fi
} >"${INSTALL_DIR}/install-manifest"

if [[ "${SNAPASSIST_SKIP_SYSTEMD:-0}" != "1" ]]; then
    # La instancia systemd del usuario no siempre hereda estas variables del
    # escritorio. Guardarlas evita asumir que el display necesariamente es :0.
    {
        printf 'DISPLAY=%q\n' "${DISPLAY}"
        printf 'XDG_SESSION_TYPE=%q\n' "${XDG_SESSION_TYPE:-x11}"
        if [[ -n "${XAUTHORITY:-}" ]]; then
            printf 'XAUTHORITY=%q\n' "${XAUTHORITY}"
        fi
    } >"${ENV_FILE}"
    chmod 0600 "${ENV_FILE}"
fi

if [[ "${SNAPASSIST_SKIP_PIP:-0}" != "1" && "${RUNTIME}" == "x11" ]]; then
    if [[ ! -x "${INSTALL_DIR}/venv/bin/python" ]]; then
        "${PYTHON_BIN}" -m venv "${INSTALL_DIR}/venv"
    fi
    "${INSTALL_DIR}/venv/bin/python" -m pip install --disable-pip-version-check \
        --requirement "${INSTALL_DIR}/requirements.txt"
fi

if [[ "${SNAPASSIST_SKIP_SYSTEMD:-0}" != "1" ]]; then
    command -v systemctl >/dev/null 2>&1 || {
        echo "Error: systemctl no está disponible; no se puede activar el servicio." >&2
        exit 1
    }
    systemctl --user daemon-reload
    if [[ "${CHANNEL}" == "stable" ]]; then
        if ! SNAPASSIST_DATA_HOME="${DATA_HOME}" \
             SNAPASSIST_CONFIG_HOME="${CONFIG_HOME}" \
             "${BIN_HOME}/snapassist-channel" stable; then
            echo "Error: no se pudo activar de forma saludable el canal stable." >&2
            journalctl --user -u "${UNIT_NAME}" -n 20 --no-pager >&2 || true
            exit 1
        fi
    fi
fi

echo "SnapAssist instalado en ${INSTALL_DIR}"
echo "Servicio: ${UNIT_DIR}/${UNIT_NAME}"
if [[ "${CHANNEL}" == "stable" && "${SNAPASSIST_SKIP_SYSTEMD:-0}" != "1" ]]; then
    echo "Estado: estable activo. Pulsa Super+Z para probarlo."
else
    echo "Canal ${CHANNEL} instalado. Actívalo con: ${BIN_HOME}/snapassist-channel ${CHANNEL}"
fi
