# SPDX-License-Identifier: MIT
"""对实际 SDK 配置生成器验证默认值、转义、重复执行和 HNAT 种子。"""

import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("prepare_wifi", REPO / "Scripts/prepare_mtk_wifi7.py")
prepare_wifi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare_wifi)


class MtkWifi7Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="h5000m-mtk-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        sdk = Path(os.environ.get("H5000M_SDK_SOURCE", REPO / "wrt"))
        self.relative = "package/mtk/applications/mtwifi-cfg-ucode/files/lib/wifi/mtwifi.uc"
        for relative in (
            self.relative,
            "package/mtk/drivers/mt_wifi7/Makefile",
            "package/mtk/drivers/mt_hwifi/Makefile",
            "package/mtk/applications/hnat-detect/Makefile",
            "target/linux/mediatek/dts/mt7987a-hiveton-h5000m.dts",
        ):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(sdk / relative, target)

    def prepare(self, **overrides):
        args = dict(root=self.root, ssid='测试 "Wi-Fi" \\ 网络', key='pa"ss\\word123',
                    encryption="psk-mixed", country="CN", width_2g=40, width_5g=160)
        args.update(overrides)
        prepare_wifi.prepare(**args)
        return args

    def test_real_generator_defaults_and_escaping(self):
        args = self.prepare()
        source = (self.root / self.relative).read_text()
        function = re.search(r"function get_band_defaults\(band\) \{.*?\n\}", source, re.S)[0]
        result = subprocess.check_output(
            ["node", "-e", function + ';process.stdout.write(JSON.stringify([get_band_defaults("2g"), get_band_defaults("5g")]));'],
            text=True,
        )
        bands = json.loads(result)
        self.assertEqual([b["htmode"] for b in bands], ["EHT40", "EHT160"])
        self.assertEqual([b["ssid"] for b in bands], [args["ssid"], args["ssid"]])
        key = re.search(r'"key":\s*("(?:[^"\\]|\\.)*")', source)[1]
        self.assertEqual(json.loads(key), args["key"])
        self.assertIn('"encryption": "psk-mixed+ccmp"', source)
        self.assertIn('cursor.set("wireless", devname, "wifi-device")', source)
        self.assertIn('let iface_name = "default_" + devname', source)

    def test_repeated_execution_updates_without_duplicate_key(self):
        self.prepare()
        self.prepare(ssid="Updated", key="new-password", country="US", encryption="sae-mixed", width_5g=80)
        source = (self.root / self.relative).read_text()
        self.assertEqual(len(re.findall(r'"key":', source)), 1)
        self.assertIn('"key": "new-password"', source)
        self.assertIn('"encryption": "sae-mixed"', source)
        self.assertIn('"country": "US"', source)
        self.assertIn('htmode: "EHT80"', source)

    def test_upstream_change_is_rejected(self):
        path = self.root / self.relative
        path.write_text(path.read_text().replace("get_band_defaults(band)", "changed_defaults(band)"))
        with self.assertRaisesRegex(ValueError, "上游无线配置结构变化"):
            self.prepare()
        self.assertFalse((self.root / "files/etc/uci-defaults/zz-h5000m-hnat").exists())

    def test_unsupported_width_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "带宽"):
            self.prepare(width_5g=320)

    def run_hnat_seed(self, engine=""):
        self.prepare()
        bindir = self.root / "bin"
        bindir.mkdir()
        log = self.root / "uci.log"
        stub = bindir / "uci"
        stub.write_text('''#!/bin/sh
printf "%s\\n" "$*" >> "$H5000M_TEST_UCI_LOG"
case "$*" in
    '-q get turboacc.config.fastpath') printf '%s\\n' "$H5000M_TEST_ENGINE" ;;
esac
exit 0
''')
        stub.chmod(0o755)
        subprocess.run(["sh", str(self.root / "files/etc/uci-defaults/zz-h5000m-hnat")],
                       check=True, env={**os.environ, "PATH": f'{bindir}:{os.environ["PATH"]}',
                                        "H5000M_TEST_UCI_LOG": str(log),
                                        "H5000M_TEST_ENGINE": engine})
        return log.read_text().splitlines()

    def test_hnat_seed_selects_one_engine(self):
        calls = self.run_hnat_seed("flow_offloading")
        self.assertIn("-q set firewall.@defaults[0].flow_offloading=0", calls)
        self.assertIn("-q set firewall.@defaults[0].flow_offloading_hw=0", calls)
        self.assertIn("-q set turboacc.config.fastpath=mediatek_hnat", calls)
        self.assertNotIn("-q set firewall.@defaults[0].flow_offloading_hw=1", calls)

    def test_hnat_seed_preserves_disabled_engine(self):
        calls = self.run_hnat_seed("disabled")
        self.assertNotIn("-q set turboacc.config.fastpath=mediatek_hnat", calls)


class ConfigMergeTests(unittest.TestCase):
    def test_feed_generated_device_defaults_do_not_enter_requested_config(self):
        workflow = (REPO / ".github/workflows/WRT-CORE.yml").read_text()
        block = workflow.split("      - name: Custom Settings\n", 1)[1]
        block = block.split("      - name: Verify Config", 1)[0]
        script = textwrap.dedent(block.split("run: |\n", 1)[1])
        with tempfile.TemporaryDirectory(prefix="h5000m-config-merge-") as temp:
            work = Path(temp)
            (work / "wrt").mkdir()
            shutil.copytree(REPO / "Config", work / "Config")
            (work / "Scripts").mkdir()
            settings = work / "Scripts/Settings.sh"
            settings.write_text("#!/bin/sh\nexit 0\n")
            settings.chmod(0o755)
            (work / "wrt/.config").write_text(
                "CONFIG_PACKAGE_modem-pro=y\nCONFIG_MODEM_PRO_HOST_RUST=y\n"
                "CONFIG_TARGET_mediatek_filogic_DEVICE_openwrt_one=y\n"
                "CONFIG_DEFAULT_kmod-phy-airoha-en8811h=y\n"
                "CONFIG_PACKAGE_u-boot-mt7981_openwrt_one-nor=y\n"
            )
            result = subprocess.run(
                ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c",
                 "make() { return 0; }\n" + script], cwd=work,
                env={**os.environ, "GITHUB_WORKSPACE": str(work),
                     "WRT_CONFIG_FILE": str(work / "Config/H5000M-modem-pro.txt"),
                     "WRT_VARIANT": "modem-pro", "WRT_VARIANT_CONFIG": "MODEM-PRO.txt"},
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            requested = (work / "wrt/.config.requested").read_text()
            self.assertNotIn("openwrt_one", requested)
            self.assertNotIn("CONFIG_DEFAULT_kmod-phy-airoha-en8811h", requested)
            self.assertIn("CONFIG_TARGET_DEVICE_mediatek_filogic_DEVICE_hiveton_h5000m=y", requested)
            self.assertIn("CONFIG_PACKAGE_modem-pro=y", requested)
            self.assertIn("CONFIG_MODEM_PRO_HOST_RUST=y", requested)


if __name__ == "__main__":
    unittest.main()
