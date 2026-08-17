#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${1:-${ROOT_DIR}/dist/release}"
PYTHON_BIN="${SNAPASSIST_BUILD_PYTHON:-/usr/bin/python3}"
VERSION="$("${PYTHON_BIN}" -c 'import snapassist; print(snapassist.__version__)' 2>/dev/null || PYTHONPATH="${ROOT_DIR}" "${PYTHON_BIN}" -c 'import snapassist; print(snapassist.__version__)')"
COMMIT="$(git -C "${ROOT_DIR}" rev-parse HEAD 2>/dev/null || printf unknown)"
BUILD_EPOCH="${SOURCE_DATE_EPOCH:-$(git -C "${ROOT_DIR}" show -s --format=%ct HEAD 2>/dev/null || date +%s)}"

for command_name in git tar gzip sha256sum gnome-extensions; do
    command -v "${command_name}" >/dev/null 2>&1 || {
        echo "Error: falta ${command_name}." >&2
        exit 1
    }
done

if [[ "${VERSION}" == "2.0.0" ]]; then
    [[ "$(git -C "${ROOT_DIR}" describe --tags --exact-match 2>/dev/null || true)" == "v2.0.0" ]] || {
        echo "Error: el release final 2.0.0 debe construirse desde el tag v2.0.0." >&2
        exit 1
    }
    [[ -z "$(git -C "${ROOT_DIR}" status --porcelain --untracked-files=normal)" ]] || {
        echo "Error: el release final requiere un árbol limpio." >&2
        exit 1
    }
fi

temporary="$(mktemp -d)"
cleanup() { rm -rf -- "${temporary}"; }
trap cleanup EXIT
artifacts="${temporary}/artifacts"
install -d "${artifacts}" "${OUTPUT_DIR}"

wheel_source="${temporary}/wheel-source"
install -d "${wheel_source}"
cp -a "${ROOT_DIR}/snapassist" "${wheel_source}/"
for item in pyproject.toml README.md LICENSE requirements.txt; do
    cp -a "${ROOT_DIR}/${item}" "${wheel_source}/"
done
SOURCE_DATE_EPOCH="${BUILD_EPOCH}" \
    "${PYTHON_BIN}" -m pip wheel --no-deps --no-build-isolation \
    --wheel-dir "${artifacts}" "${wheel_source}"
SOURCE_DATE_EPOCH="${BUILD_EPOCH}" \
    bash "${ROOT_DIR}/scripts/build-gnome-extension.sh" --channel test "${artifacts}"
SOURCE_DATE_EPOCH="${BUILD_EPOCH}" \
    bash "${ROOT_DIR}/scripts/build-gnome-extension.sh" --channel stable "${artifacts}"

source_stage="${temporary}/snapassist-${VERSION}"
install -d "${source_stage}"
for item in snapassist gnome-extension protocol scripts docs tests .github; do
    cp -a "${ROOT_DIR}/${item}" "${source_stage}/"
done
for item in install.sh snapassist.service snapassist-channel snapassist-manage pyproject.toml requirements.txt README.md LICENSE CHANGELOG.md ROADMAP.md PLAN_EVOLUCION_1.1_A_2.0.md; do
    cp -a "${ROOT_DIR}/${item}" "${source_stage}/"
done
find "${source_stage}" -type d -name __pycache__ -prune -exec rm -rf -- {} +
find "${source_stage}" -exec touch -d "@${BUILD_EPOCH}" {} +
tar --sort=name --mtime="@${BUILD_EPOCH}" --owner=0 --group=0 --numeric-owner \
    -C "${temporary}" -cf - "snapassist-${VERSION}" | gzip -n > "${artifacts}/snapassist-${VERSION}-source.tar.gz"

dirty=false
if ! git -C "${ROOT_DIR}" diff --quiet --ignore-submodules HEAD || \
   [[ -n "$(git -C "${ROOT_DIR}" ls-files --others --exclude-standard)" ]]; then
    dirty=true
fi
"${PYTHON_BIN}" -c 'import json, pathlib, sys; path=pathlib.Path(sys.argv[1]); value={"schemaVersion":1,"product":"SnapAssist","version":sys.argv[2],"commit":sys.argv[3],"sourceDirty":sys.argv[4] == "true","sourceDateEpoch":int(sys.argv[5]),"baselineCommit":"77a6e66","protocolVersion":1,"gnomeShellVersions":["46"],"artifacts":{"daemon":"wheel","extensionStable":"snapassist@oscaragredav","extensionTest":"snapassist-test@oscaragredav"}}; path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")' \
    "${artifacts}/release-manifest.json" "${VERSION}" "${COMMIT}" "${dirty}" "${BUILD_EPOCH}"

(
    cd "${artifacts}"
    sha256sum -- * | sort -k2 > SHA256SUMS
)
find "${artifacts}" -exec touch -d "@${BUILD_EPOCH}" {} +
bundle="${OUTPUT_DIR}/snapassist-${VERSION}-bundle.tar.gz"
tar --sort=name --mtime="@${BUILD_EPOCH}" --owner=0 --group=0 --numeric-owner \
    -C "${artifacts}" -cf - . | gzip -n > "${bundle}"
cp -a "${artifacts}/release-manifest.json" "${OUTPUT_DIR}/"
cp -a "${artifacts}/SHA256SUMS" "${OUTPUT_DIR}/"
sha256sum "${bundle}" > "${bundle}.sha256"
echo "Bundle creado: ${bundle}"
