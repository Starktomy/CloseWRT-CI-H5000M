#!/bin/bash
# SPDX-License-Identifier: MIT
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/H5000M-Profiles.sh"
h5000m_profile "${1:?configuration is required}"
BUILD_ROOT="$(cd "${2:?OpenWrt directory is required}" && pwd)"

if [ "$H5000M_RUST_FAN" = 1 ]; then
	(
		cd "$BUILD_ROOT/package/luci-app-h5000m-fancontrol"
		node tests/frontend-smoke.js
		node scripts/i18n-audit.js
		sh tests/test-uci-defaults.sh
		sh tests/test-kernel-safety.sh
		sh tests/test-packaging.sh
	)
fi

case "$WRT_VARIANT" in
	mt5700)
		(
			cd "$BUILD_ROOT/package/luci-app-mt5700"
			node tests/static-check.js
			for test in tests/*-test.js; do node "$test"; done
		)
		;;
	mt5700m)
		(
			cd "$BUILD_ROOT/package/luci-app-mt5700m"
			for test in luci-app-mt5700m/tests/*.sh; do sh "$test"; done
			transport="$(mktemp -d)"
			trap 'rm -rf "$transport"' EXIT
			gcc -O2 -Wall -Wextra -Werror mt5700m-transport/src/transport.c -o "$transport/mt5700m-transport"
			TRANSPORT_BIN="$transport/mt5700m-transport" python3 mt5700m-transport/tests/test_transport.py
		)
		;;
esac
