#!/bin/bash
# SPDX-License-Identifier: MIT
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/H5000M-Profiles.sh"
h5000m_profile "${1:?configuration is required}"
BUILD_ROOT="$(cd "${2:?OpenWrt directory is required}" && pwd)"
[ "$H5000M_RUST_FAN" = 1 ] || exit 0

# 在线升级后端的预编译步骤已准备好宿主 Rust 和 OpenWrt musl 工具链。
export PATH="$HOME/.cargo/bin:$PATH"
export RUSTUP_TOOLCHAIN=stable
rustup target add aarch64-unknown-linux-musl
FAN_DIR="$BUILD_ROOT/package/luci-app-h5000m-fancontrol"

validate_binary() {
	file "$1"
	file "$1" | grep -Eq 'ELF 64-bit.*ARM aarch64.*(statically linked|static-pie linked)'
	# 静态 PIE 可有动态段，但不能有动态加载器或共享库依赖。
	if readelf -l "$1" | grep -q 'INTERP' || readelf -d "$1" 2>/dev/null | grep -q '(NEEDED)'; then
		echo "::error::后端不是独立静态二进制：$1" >&2
		return 1
	fi
}

(
	cd "$FAN_DIR/src"
	cargo test --locked --offline --release
	CARGO_TARGET_DIR="$BUILD_ROOT/.rust-build/fancontrol/target" \
		cargo build --locked --offline --release --target aarch64-unknown-linux-musl
)
FAN_BINARY="$BUILD_ROOT/.rust-build/fancontrol/target/aarch64-unknown-linux-musl/release/h5000m-fancontrol"
validate_binary "$FAN_BINARY"
python3 "$SCRIPT_DIR/install_prebuilt.py" --package "$FAN_DIR" --binary "$FAN_BINARY" \
	--install /usr/sbin/h5000m-fancontrol

if [ "$WRT_VARIANT" = mt5700 ]; then
	MODEM_DIR="$BUILD_ROOT/package/luci-app-mt5700"
	LINKER="$(find "$BUILD_ROOT/staging_dir" -type f -name aarch64-openwrt-linux-musl-gcc -perm -111 -print -quit)"
	[ -n "$LINKER" ] || { echo '::error::未找到 aarch64 musl 交叉链接器'; exit 1; }
	LINKER="$(readlink -f "$LINKER")"
	TOOL_BIN="$(dirname "$LINKER")"
	export CARGO_TARGET_AARCH64_UNKNOWN_LINUX_MUSL_LINKER="$LINKER"
	export CC_aarch64_unknown_linux_musl="$LINKER"
	export AR_aarch64_unknown_linux_musl="$TOOL_BIN/aarch64-openwrt-linux-musl-ar"
	export MT5700_VERSION
	MT5700_VERSION="$(sed -n 's/^PKG_VERSION:=//p' "$MODEM_DIR/Makefile" | head -n1)"
	(
		cd "$MODEM_DIR/src/rust"
		CARGO_TARGET_DIR="$BUILD_ROOT/.rust-build/mt5700/target" \
			cargo build --locked --release --target aarch64-unknown-linux-musl
	)
	MODEM_BINARY="$BUILD_ROOT/.rust-build/mt5700/target/aarch64-unknown-linux-musl/release/at-webserver"
	validate_binary "$MODEM_BINARY"
	python3 "$SCRIPT_DIR/install_prebuilt.py" --package "$MODEM_DIR" --binary "$MODEM_BINARY" \
		--install /usr/bin/at-webserver-rust
fi
