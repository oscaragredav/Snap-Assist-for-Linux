#!/usr/bin/env bash
set -euo pipefail

# Instalador idempotente de SnapAssist para el usuario actual.
# Las variables SNAPASSIST_* permiten probarlo en un árbol temporal sin tocar
# el home real; no son necesarias durante una instalación normal.
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DATA_HOME="${SNAPASSIST_DATA_HOME:-${XDG_DATA_HOME:-${HOME}/.local/share}}"
CONFIG_HOME="${SNAPASSIST_CONFIG_HOME:-${XDG_CONFIG_HOME:-${HOME}/.config}}"
INSTALL_DIR="${DATA_HOME}/snapassist"
UNIT_DIR="${CONFIG_HOME}/systemd/user"
APP_CONFIG_DIR="${CONFIG_HOME}/snapassist"
ENV_FILE="${APP_CONFIG_DIR}/environment"
PYTHON_BIN="${SNAPASSIST_PYTHON:-python3}"

command -v "${PYTHON_BIN}" >/dev/null 2>&1 || {
    echo "Error: no se encontró ${PYTHON_BIN}. Instala Python 3.11 o superior." >&2
    exit 1
}

"${PYTHON_BIN}" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' || {
    echo "Error: SnapAssist requiere Python 3.11 o superior." >&2
    exit 1
}

"${PYTHON_BIN}" -c 'import tkinter' >/dev/null 2>&1 || {
    echo "Error: falta tkinter. En Zorin/Ubuntu instala python3-tk." >&2
    exit 1
}

if [[ "${SNAPASSIST_SKIP_SYSTEMD:-0}" != "1" ]]; then
    if [[ "${XDG_SESSION_TYPE:-x11}" != "x11" ]]; then
        echo "Error: SnapAssist todavía requiere una sesión X11 (sesión actual: ${XDG_SESSION_TYPE:-desconocida})." >&2
        echo "Cierra sesión, selecciona una sesión con Xorg/X11 en la pantalla de acceso y vuelve a intentarlo." >&2
        exit 1
    fi
    if [[ -z "${DISPLAY:-}" ]]; then
        echo "Error: DISPLAY no está definido. Ejecuta install.sh desde una terminal abierta dentro de tu sesión X11." >&2
        exit 1
    fi
fi

install -d "${INSTALL_DIR}" "${UNIT_DIR}" "${APP_CONFIG_DIR}"
cp -a "${SOURCE_DIR}/snapassist" "${INSTALL_DIR}/"
install -m 0644 "${SOURCE_DIR}/requirements.txt" "${INSTALL_DIR}/requirements.txt"
install -m 0644 "${SOURCE_DIR}/README.md" "${INSTALL_DIR}/README.md"
install -m 0644 "${SOURCE_DIR}/LICENSE" "${INSTALL_DIR}/LICENSE"
install -m 0644 "${SOURCE_DIR}/CHANGELOG.md" "${INSTALL_DIR}/CHANGELOG.md"
install -m 0644 "${SOURCE_DIR}/pyproject.toml" "${INSTALL_DIR}/pyproject.toml"
unit_template="$(<"${SOURCE_DIR}/snapassist.service")"
unit_template="${unit_template//@INSTALL_DIR@/${INSTALL_DIR}}"
unit_template="${unit_template//@ENV_FILE@/${ENV_FILE}}"
printf '%s\n' "${unit_template}" >"${UNIT_DIR}/snapassist.service"

if [[ "${SNAPASSIST_SKIP_SYSTEMD:-0}" != "1" ]]; then
    # La instancia systemd del usuario no siempre hereda estas variables del
    # escritorio. Guardarlas evita asumir que el display necesariamente es :0.
    {
        printf 'DISPLAY=%q\n' "${DISPLAY}"
        printf 'XDG_SESSION_TYPE=x11\n'
        if [[ -n "${XAUTHORITY:-}" ]]; then
            printf 'XAUTHORITY=%q\n' "${XAUTHORITY}"
        fi
    } >"${ENV_FILE}"
    chmod 0600 "${ENV_FILE}"
fi

if [[ "${SNAPASSIST_SKIP_PIP:-0}" != "1" ]]; then
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
    systemctl --user enable snapassist.service
    systemctl --user restart snapassist.service
    if ! systemctl --user is-active --quiet snapassist.service; then
        echo "Error: el servicio se instaló, pero no pudo iniciarse. Últimos mensajes:" >&2
        journalctl --user -u snapassist.service -n 20 --no-pager >&2 || true
        exit 1
    fi
fi

echo "SnapAssist instalado en ${INSTALL_DIR}"
echo "Servicio: ${UNIT_DIR}/snapassist.service"
echo "Estado: activo. Pulsa Super+Z para probarlo."
