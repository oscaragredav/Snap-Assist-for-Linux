#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export SNAPASSIST_CHANNEL=test
export SNAPASSIST_CONFIG_FILE="${XDG_CONFIG_HOME:-${HOME}/.config}/snapassist-test/settings.json"
export SNAPASSIST_LOG_DIR="${XDG_DATA_HOME:-${HOME}/.local/share}/snapassist-test/logs"
export PYTHONPATH="${ROOT_DIR}${PYTHONPATH:+:${PYTHONPATH}}"

exec /usr/bin/python3 -m snapassist.gnome_main
