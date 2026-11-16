#!/bin/bash
# SPDX-License-Identifier: MIT
# H5000M 构建方案的唯一映射；供工作流、包选择与验证共用。

h5000m_profile() {
	case "${1:-}" in
		H5000M-qmodem-next)
			WRT_VARIANT=qmodem-next
			WRT_VARIANT_CONFIG=QMODEM-NEXT.txt
			H5000M_FANCONTROL_REPO=LianXia233/luci-app-h5000m-fancontrol
			;;
		H5000M-qmodem)
			WRT_VARIANT=qmodem
			WRT_VARIANT_CONFIG=QMODEM.txt
			H5000M_FANCONTROL_REPO=FAN789/luci-app-h5000m-fancontrol
			;;
		H5000M-modem-pro)
			WRT_VARIANT=modem-pro
			WRT_VARIANT_CONFIG=MODEM-PRO.txt
			H5000M_FANCONTROL_REPO=FAN789/luci-app-h5000m-fancontrol
			;;
		H5000M-mt5700)
			WRT_VARIANT=mt5700
			WRT_VARIANT_CONFIG=MT5700.txt
			H5000M_FANCONTROL_REPO=LianXia233/luci-app-h5000m-fancontrol
			;;
		H5000M-mt5700m)
			WRT_VARIANT=mt5700m
			WRT_VARIANT_CONFIG=MT5700M.txt
			H5000M_FANCONTROL_REPO=FAN789/luci-app-h5000m-fancontrol
			;;
		*)
			echo "::error::不支持的 H5000M 配置 '${1:-}'" >&2
			return 1
			;;
	esac
	H5000M_RUST_FAN=0
	if [ "$H5000M_FANCONTROL_REPO" = LianXia233/luci-app-h5000m-fancontrol ]; then
		H5000M_RUST_FAN=1
	fi
	export WRT_VARIANT WRT_VARIANT_CONFIG H5000M_FANCONTROL_REPO H5000M_RUST_FAN
}
