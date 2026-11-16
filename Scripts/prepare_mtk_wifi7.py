#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""适配 H5000M 的 mtwifi-cfg-ucode 出厂参数与 HNAT 初始设置。"""

import argparse
import json
from pathlib import Path
import re


def replace_once(text, pattern, replacement):
    updated, count = re.subn(pattern, lambda match: replacement(match), text, flags=re.S)
    if count != 1:
        raise ValueError(f"上游无线配置结构变化：{pattern!r} 匹配 {count} 次")
    return updated


def prepare(root, ssid, key, encryption, country, width_2g, width_5g):
    for relative in (
        "package/mtk/drivers/mt_wifi7/Makefile",
        "package/mtk/drivers/mt_hwifi/Makefile",
        "package/mtk/applications/hnat-detect/Makefile",
        "target/linux/mediatek/dts/mt7987a-hiveton-h5000m.dts",
    ):
        if not (root / relative).is_file():
            raise ValueError(f"源码不属于预期的 H5000M Wi-Fi 7 SDK：缺少 {relative}")
    if not re.fullmatch(r"[A-Z]{2}", country):
        raise ValueError("无线国家码必须是两个大写字母")
    if width_2g not in (20, 40) or width_5g not in (20, 40, 80, 160):
        raise ValueError("H5000M 无线带宽超出支持范围")
    if not 1 <= len(ssid.encode()) <= 32 or not 8 <= len(key.encode()) <= 63:
        raise ValueError("SSID 必须为 1—32 字节，无线密钥必须为 8—63 字节")
    if encryption not in ("psk2", "psk-mixed", "sae", "sae-mixed"):
        raise ValueError(f"不支持的加密方式：{encryption}")
    if encryption in ("psk2", "psk-mixed"):
        encryption += "+ccmp"

    literal = lambda value: json.dumps(value, ensure_ascii=False)
    path = root / "package/mtk/applications/mtwifi-cfg-ucode/files/lib/wifi/mtwifi.uc"
    source = path.read_text()
    function = f'''function get_band_defaults(band) {{
    if (band == "2g") {{
        return {{ htmode: "EHT{width_2g}", htbsscoex: 1, ssid: {literal(ssid)} }};
    }} else if (band == "5g") {{
        return {{ htmode: "EHT{width_5g}", htbsscoex: 0, ssid: {literal(ssid)} }};
    }} else {{
        return {{ htmode: "EHT{width_5g}", htbsscoex: 0, ssid: {literal(ssid)} }};
    }}
}}'''
    source = replace_once(source, r"function get_band_defaults\(band\) \{.*?\n\}", lambda _: function)
    source = replace_once(source, r'"country":\s*"(?:[^"\\]|\\.)*"',
                          lambda _: f'"country": {literal(country)}')
    source = replace_once(
        source,
        r'"encryption":\s*"(?:[^"\\]|\\.)*"(?:,\n\s*"key":\s*"(?:[^"\\]|\\.)*")?',
        lambda _: f'"encryption": {literal(encryption)},\n        "key": {literal(key)}',
    )
    path.write_text(source)

    defaults = root / "files/etc/uci-defaults/zz-h5000m-hnat"
    defaults.parent.mkdir(parents=True, exist_ok=True)
    defaults.write_text('''#!/bin/sh
# SPDX-License-Identifier: MIT
# 首次启动采用 SDK HNAT，避免与标准 flowtable/PPE 同时操作硬件。
uci -q set firewall.@defaults[0].flow_offloading=0 || exit 1
uci -q set firewall.@defaults[0].flow_offloading_hw=0 || exit 1
uci -q commit firewall || exit 1
if uci -q get turboacc.config >/dev/null; then
    # 保留用户明确禁用加速的选择；只迁移空值或旧 flowtable 引擎。
    case "$(uci -q get turboacc.config.fastpath)" in
        ''|flow_offloading)
            uci -q set turboacc.config.fastpath=mediatek_hnat || exit 1
            uci -q commit turboacc || exit 1
            ;;
    esac
fi
exit 0
''')
    defaults.chmod(0o755)
    print(f"mtwifi defaults: EHT{width_2g}/EHT{width_5g}, country={country}, encryption={encryption}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--ssid", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--encryption", required=True)
    parser.add_argument("--country", required=True)
    parser.add_argument("--width-2g", required=True, type=int)
    parser.add_argument("--width-5g", required=True, type=int)
    args = parser.parse_args()
    prepare(args.root, args.ssid, args.key, args.encryption, args.country, args.width_2g, args.width_5g)


if __name__ == "__main__":
    main()
