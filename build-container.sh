#!/usr/bin/env bash
# Quick local container build for hands-on testing.
#
# Brands the image with the current git-derived version (same scheme CI uses).
# Override the image name/tag via env:  IMAGE=labeljetty TAG=dev ./build-container.sh
# Extra args are passed through to `docker build`, e.g.:  ./build-container.sh --no-cache
set -euo pipefail

# Use the exact version tag if HEAD sits on one; otherwise a PEP440-valid local
# marker (setuptools_scm/SETUPTOOLS_SCM_PRETEND_VERSION rejects raw `git describe`
# output like "abc1234-dirty"). CI uses the release tag directly, so it's always clean.
VERSION="$(git describe --tags --exact-match --match '[0-9]*' 2>/dev/null || true)"
VERSION="${VERSION#v}"
if [ -z "${VERSION}" ]; then
  VERSION="0.0.0+local.$(git rev-parse --short HEAD 2>/dev/null || echo dev)"
fi
IMAGE="${IMAGE:-labeljetty}"
TAG="${TAG:-dev}"

echo "Building ${IMAGE}:${TAG}  (VERSION=${VERSION})"
docker build --build-arg "VERSION=${VERSION}" -t "${IMAGE}:${TAG}" "$@" .

cat <<EOF

Built ${IMAGE}:${TAG}

Run it (adjust PRINTER_USB and the USB device path):
  docker run --rm -p 8888:8888 \\
    --device=/dev/bus/usb \\
    -e PRINTER_USB=vid:2d37:pid:62de \\
    -v "\$(pwd)/data:/data" \\
    ${IMAGE}:${TAG}
EOF
