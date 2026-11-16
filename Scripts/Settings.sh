#!/bin/bash
# SPDX-License-Identifier: MIT
# Copyright (C) 2026 VIKINGYFY
set -e -o pipefail

#移除luci-app-attendedsysupgrade
sed -i "/attendedsysupgrade/d" $(find ./feeds/luci/collections/ -type f -name "Makefile")
#修改默认主题
sed -i "s/luci-theme-bootstrap/luci-theme-$WRT_THEME/g" $(find ./feeds/luci/collections/ -type f -name "Makefile")
#修改immortalwrt.lan关联IP
sed -i "s/192\.168\.[0-9]*\.[0-9]*/$WRT_IP/g" $(find ./feeds/luci/modules/luci-mod-system/ -type f -name "flash.js")
#添加编译日期标识
sed -i "s/(\(luciversion || ''\))/(\1) + (' \/ $WRT_MARK-$WRT_DATE')/g" $(find ./feeds/luci/modules/luci-mod-status/ -type f -name "10_system.js")

# mtwifi-cfg-ucode 使用 l1profile 动态设备名，在生成 UCI 配置时注入默认参数。
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "$SCRIPT_DIR/prepare_mtk_wifi7.py" --root "$PWD" \
    --ssid "$WRT_SSID" --key "$WRT_WORD" \
    --encryption "${WIFI_ENCRYPTION:-psk-mixed}" --country "${WIFI_COUNTRY:-CN}" \
    --width-2g "${WIFI_2G_WIDTH:-40}" --width-5g "${WIFI_5G_WIDTH:-160}"

# ===== 在线升级插件：按机型生成出厂预设 =====
# 必须在 make defconfig 之前执行：此刻 .config 已含 Config/GENERAL.txt 的
# CONFIG_PACKAGE_luci-app-online-upgrade=y，脚本据此决定是否生成
# ./files/etc/config/online-upgrade（覆盖包自带的 conffile）。
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
bash "$SCRIPT_DIR/OnlineUpgradePreset.sh"

CFG_FILE="./package/base-files/files/bin/config_generate"
#修改默认IP地址
sed -i "s/192\.168\.[0-9]*\.[0-9]*/$WRT_IP/g" $CFG_FILE
#修改默认主机名
sed -i "s/hostname='.*'/hostname='$WRT_NAME'/g" $CFG_FILE
#修改默认时区（由 Config/OWRT-DEFAULT.txt 的 WRT_TIMEZONE / WRT_ZONENAME 驱动）
sed -i "s/timezone='GMT0'/timezone='${WRT_TIMEZONE:-CST-8}'/g" $CFG_FILE
# zonename 含 "/"（Asia/Shanghai），必须换用 | 作分隔符；否则 sed 报
# "unknown option to `s'"，时区名静默保留为 UTC（run #133 日志中即此报错）
sed -i "s|zonename='UTC'|zonename='${WRT_ZONENAME:-Asia/Shanghai}'|g" $CFG_FILE

#配置文件修改
echo "CONFIG_PACKAGE_luci=y" >> ./.config
echo "CONFIG_LUCI_LANG_zh_Hans=y" >> ./.config
echo "CONFIG_PACKAGE_luci-theme-$WRT_THEME=y" >> ./.config

# ===== 主题配套包 =====
# 默认主题由 WRT_THEME 决定（当前 vantage）；luci-theme-bootstrap 已在脚本开头被
# 替换成 luci-theme-$WRT_THEME，故未安装的主题不会抢占默认样式。
# 各主题的配套包名并不统一（aurora → luci-app-aurora-config、vantage →
# luci-app-vantage 仪表盘、argon → luci-app-argon-config），无脑拼
# luci-app-$WRT_THEME-config 会写出不存在的符号；这类符号在 defconfig 阶段被
# 静默丢弃，直接触发 check_defconfig.py 的「请求 y 却未生效」硬断言（构建失败）。
THEME_PKG=""
case "$WRT_THEME" in
	aurora)  THEME_PKG="luci-app-aurora-config" ;;
	vantage) THEME_PKG="luci-app-vantage" ;;
	argon)   THEME_PKG="luci-app-argon-config" ;;
esac
if [ -n "$THEME_PKG" ]; then
	echo "CONFIG_PACKAGE_$THEME_PKG=y" >> ./.config
fi

# Aurora 保留为可选主题（编入固件但不再默认），可在「系统 → 语言和界面」切回
if [ "$WRT_THEME" != "aurora" ]; then
	echo "CONFIG_PACKAGE_luci-theme-aurora=y" >> ./.config
	echo "CONFIG_PACKAGE_luci-app-aurora-config=y" >> ./.config
fi

# ===== 默认主题种子（首启动 uci-defaults）=====
# 集合依赖换成 luci-theme-$WRT_THEME 只能保证「该主题被安装」，无法保证
# /etc/config/luci 的 mediaurlbase 指向它：该文件是 conffile，sysupgrade 保留旧
# 配置时仍写着上一代默认（/luci-static/aurora），而主题包自带的 30_luci-theme-*
# 脚本只在 luci.themes.<Name> 首次注册时才写 mediaurlbase，升级路径不会切换。
# 这里生成一个排在 30_* 之后执行的种子脚本：
#   - 主题目录不存在（未编入）则不动配置，避免留下坏路径；
#   - 用 luci.main.theme_seeded 记录已种子过的默认主题，同一代主题只种一次，
#     用户此后在 LuCI 里改的主题不会被每次升级重置；日后更换默认主题时该值
#     不等，种子脚本会重新生效。
THEME_SEED_DIR="./files/etc/uci-defaults"
mkdir -p "$THEME_SEED_DIR"
THEME_NAME="$(printf '%s' "${WRT_THEME:0:1}" | tr '[:lower:]' '[:upper:]')${WRT_THEME:1}"
cat > "$THEME_SEED_DIR/40-luci-default-theme" <<EOF
#!/bin/sh
# 出厂默认主题：构建时由 Scripts/Settings.sh 依据 WRT_THEME 生成，勿手改
THEME='$WRT_THEME'
THEME_NAME='$THEME_NAME'

[ -n "\$THEME" ] || exit 0
[ -d "/www/luci-static/\$THEME" ] || exit 0
[ "\$(uci -q get luci.main.theme_seeded)" = "\$THEME" ] && exit 0

uci -q set "luci.themes.\$THEME_NAME=/luci-static/\$THEME"
uci -q set luci.main.mediaurlbase="/luci-static/\$THEME"
uci -q set luci.main.theme_seeded="\$THEME"
uci -q commit luci
exit 0
EOF
chmod +x "$THEME_SEED_DIR/40-luci-default-theme"
echo "default theme seeded: $WRT_THEME"

# ===== kmod-nft-fullcone 按源码实际能力裁剪 =====
# 该内核模块由 immortalwrt 系源码提供（package/network/utils/fullconenat-nft，
# 且 firewall4 自身 DEPENDS:=+kmod-nft-fullcone，两个分支都会自动编入）；
# 但 VIKINGYFY/immortalwrt 改用 fullconenat-sonic 内核补丁实现 fullcone
# （firewall4 默认 option fullcone 1），树里根本没有这个包。
# 请求树中不存在的符号会被 defconfig 静默丢弃，Verify Config 直接判失败
# （run #133 的 H5000M-modem-pro 即此因）。这里以源码树中的包定义为准：
# 找不到 KernelPackage/nft-fullcone 就删掉请求，避免误报。
if ! grep -rqs --include=Makefile "KernelPackage/nft-fullcone" ./package/; then
	sed -i "/^CONFIG_PACKAGE_kmod-nft-fullcone=/d" ./.config
	echo "kmod-nft-fullcone: 当前源码未提供该包（fullcone 由源码内置方案实现），已从请求配置移除"
fi

#引入私有扩展配置
if [ -f "$GITHUB_WORKSPACE/Config/PRIVATE.txt" ]; then
	echo "Applying private configurations from PRIVATE.txt..."
	cat $GITHUB_WORKSPACE/Config/PRIVATE.txt >> ./.config
fi

#手动调整的插件
if [ -n "$WRT_PACKAGE" ]; then
	echo -e "$WRT_PACKAGE" >> ./.config
fi
