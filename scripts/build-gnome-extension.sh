#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="${ROOT_DIR}/gnome-extension"
OUTPUT_DIR="${ROOT_DIR}/dist"
CHANNEL="test"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --channel) CHANNEL="${2:-}"; shift 2 ;;
        *) OUTPUT_DIR="$1"; shift ;;
    esac
done
[[ "${CHANNEL}" == "stable" || "${CHANNEL}" == "test" ]] || {
    echo "Error: --channel debe ser stable o test." >&2
    exit 2
}

command -v gnome-extensions >/dev/null 2>&1 || {
    echo "Error: gnome-extensions no está disponible." >&2
    exit 1
}

install -d "${OUTPUT_DIR}"
temporary="$(mktemp -d)"
PACKAGE_SOURCE="${temporary}/gnome-extension"
cp -a "${SOURCE_DIR}" "${PACKAGE_SOURCE}"
SCHEMA_FILE="schemas/org.snapassist.shell.test.gschema.xml"
EXTENSION_UUID="snapassist-test@oscaragredav"
cleanup() {
    rm -rf -- "${temporary}"
}
trap cleanup EXIT
if [[ "${CHANNEL}" == "stable" ]]; then
    /usr/bin/python3 -c 'import json, pathlib, sys; path=pathlib.Path(sys.argv[1]); value=json.loads(path.read_text()); value.update({"uuid":"snapassist@oscaragredav","name":"SnapAssist","description":"SnapAssist native integration for GNOME Shell 46","settings-schema":"org.snapassist.shell","snapassist-channel":"stable","version":20000}); path.write_text(json.dumps(value, indent=2) + "\n")' "${PACKAGE_SOURCE}/metadata.json"
    cp "${PACKAGE_SOURCE}/schemas/org.snapassist.shell.test.gschema.xml" \
        "${PACKAGE_SOURCE}/schemas/org.snapassist.shell.gschema.xml"
    sed -i \
        -e 's/org\.snapassist\.shell\.test/org.snapassist.shell/g' \
        -e 's#/org/snapassist/shell/test/#/org/snapassist/shell/#g' \
        "${PACKAGE_SOURCE}/schemas/org.snapassist.shell.gschema.xml"
    rm "${PACKAGE_SOURCE}/schemas/org.snapassist.shell.test.gschema.xml"
    SCHEMA_FILE="schemas/org.snapassist.shell.gschema.xml"
    EXTENSION_UUID="snapassist@oscaragredav"
fi
build_epoch="${SOURCE_DATE_EPOCH:-$(git -C "${ROOT_DIR}" show -s --format=%ct HEAD 2>/dev/null || date +%s)}"
find "${PACKAGE_SOURCE}" -exec touch -d "@${build_epoch}" {} +
gnome-extensions pack \
    --force \
    --out-dir "${OUTPUT_DIR}" \
    --extra-source lib \
    --extra-source protocol \
    --schema "${SCHEMA_FILE}" \
    "${PACKAGE_SOURCE}"

archive="${OUTPUT_DIR}/${EXTENSION_UUID}.shell-extension.zip"
[[ -f "${archive}" ]] || {
    echo "Error: no se creó ${archive}." >&2
    exit 1
}
/usr/bin/python3 -c 'import datetime, os, pathlib, sys, zipfile; path=pathlib.Path(sys.argv[1]); epoch=int(sys.argv[2]); stamp=datetime.datetime.fromtimestamp(max(epoch, 315532800), datetime.timezone.utc).timetuple()[:6]; temporary=path.with_suffix(".deterministic.zip"); source=zipfile.ZipFile(path); target=zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9); [(lambda data, info: target.writestr(info, data))(source.read(item.filename), (lambda info: (setattr(info, "date_time", stamp), setattr(info, "compress_type", zipfile.ZIP_DEFLATED), setattr(info, "external_attr", item.external_attr), info)[-1])(zipfile.ZipInfo(item.filename))) for item in sorted(source.infolist(), key=lambda value: value.filename)]; target.close(); source.close(); os.replace(temporary, path)' "${archive}" "${build_epoch}"
echo "Extensión creada: ${archive}"
