#!/bin/bash
# SPDX-License-Identifier: MIT
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/H5000M-Profiles.sh"
h5000m_profile "${1:?configuration is required}"
BUILD_ROOT="$(cd "${2:?OpenWrt directory is required}" && pwd)"

require_files() {
	local directory=$1 file
	shift
	for file in "$@"; do
		if [ ! -s "$directory/$file" ]; then
			echo "::error::软件包缺少 $directory/$file" >&2
			return 1
		fi
	done
}

version_of() {
	sed -n 's/^PKG_VERSION:=//p' "$1/Makefile" | head -n1
}

record() {
	printf '%s=%s\n' "$1" "$2"
	if [ -n "${GITHUB_ENV:-}" ]; then
		printf '%s=%s\n' "$1" "$2" >> "$GITHUB_ENV"
	fi
}

FAN_DIR="$BUILD_ROOT/package/luci-app-h5000m-fancontrol"
require_files "$FAN_DIR" Makefile root/etc/config/h5000m_fancontrol \
	root/etc/init.d/h5000m-fancontrol root/usr/sbin/h5000m-fancontrol-status
if [ "$H5000M_RUST_FAN" = 1 ]; then
	require_files "$FAN_DIR" src/Makefile src/Cargo.toml src/Cargo.lock \
		root/etc/uci-defaults/91-h5000m-fancontrol-v3
	# QModem Next 读取既有 /tmp/cache_* 温度；不连接 MT5700 专用 RPC。
	if [ "$WRT_VARIANT" = qmodem-next ] && ! grep -q 'H5000M_FAN_MT5700M_RPC_PORT=0' "$FAN_DIR/root/etc/init.d/h5000m-fancontrol"; then
		sed -i '/procd_set_param command \/usr\/sbin\/h5000m-fancontrol daemon/a\	procd_set_param env H5000M_FAN_MT5700M_RPC_PORT=0' \
			"$FAN_DIR/root/etc/init.d/h5000m-fancontrol"
		grep -q 'H5000M_FAN_MT5700M_RPC_PORT=0' "$FAN_DIR/root/etc/init.d/h5000m-fancontrol"
	fi
else
	require_files "$FAN_DIR" root/usr/sbin/h5000m-fancontrol
fi
record H5000M_FANCONTROL_VERSION "$H5000M_FANCONTROL_REPO $(version_of "$FAN_DIR")"

record H5000M_MODEM_VERSION "$WRT_VARIANT"

case "$WRT_VARIANT" in
	mt5700)
		MODEM_DIR="$BUILD_ROOT/package/luci-app-mt5700"
		require_files "$MODEM_DIR" Makefile src/Makefile src/rust/Cargo.toml src/rust/Cargo.lock \
			root/etc/init.d/at-webserver root/usr/share/rpcd/ucode/mt5700.uc \
			root/usr/share/luci/menu.d/luci-app-mt5700.json \
			root/usr/share/rpcd/acl.d/luci-app-mt5700.json
		record H5000M_MODEM_VERSION "LianXia233/luci-app-mt5700 $(version_of "$MODEM_DIR")"
		;;
	mt5700m)
		MODEM_DIR="$BUILD_ROOT/package/luci-app-mt5700m"
		require_files "$MODEM_DIR" luci-app-mt5700m/Makefile mt5700m-transport/Makefile \
			mt5700m-transport/src/transport.c luci-app-mt5700m/root/usr/sbin/mt5700m-manager
		record H5000M_MODEM_VERSION "FAN789/luci-app-mt5700m $(version_of "$MODEM_DIR/luci-app-mt5700m")"
		;;
esac

# 修复打包时丢失的脚本执行位，保留前端、源码和版权信息。
package_roots=("$FAN_DIR/root")
if [ -n "${MODEM_DIR:-}" ]; then
	package_roots+=("$MODEM_DIR/root" "$MODEM_DIR/luci-app-mt5700m/root")
fi
for directory in "${package_roots[@]}"; do
	[ -d "$directory" ] || continue
	for subdir in etc/init.d etc/uci-defaults etc/hotplug.d usr/sbin usr/libexec; do
		[ ! -d "$directory/$subdir" ] || find "$directory/$subdir" -type f -exec chmod 0755 {} +
	done
done
