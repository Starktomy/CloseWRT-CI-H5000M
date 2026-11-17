# SPDX-License-Identifier: MIT
"""执行实际启动脚本，复现空 factory、错误芯片、短读取与备用文件失效。"""
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'Scripts/files/h5000m-wifi-e2p.init'


class WifiEepromTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='h5000m-eeprom-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.factory = self.root / 'factory'
        self.fallback = self.root / 'BE5040.bin'
        self.output = self.root / 'e2p'
        self.data = b'\x92\x79' + b'\x17' * 7678
        self.fallback.write_bytes(self.data)

    def run_boot(self):
        before = self.factory.read_bytes() if self.factory.exists() else None
        result = subprocess.run(['sh', '-c', '. "$1"; h5000m_prepare_eeprom "$2" "$3" "$4"',
                                 'eeprom-test', str(SCRIPT), str(self.factory), str(self.fallback), str(self.output)],
                                capture_output=True, text=True)
        self.assertEqual(self.factory.read_bytes() if self.factory.exists() else None, before)
        return result

    def test_valid_factory_wins_and_is_never_written(self):
        data = b'\x92\x79' + b'\x34' * 7678
        self.factory.write_bytes(data + b'partition-tail')
        result = self.run_boot()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.read_bytes(), data)
        self.assertIn('factory ->', result.stdout)

    def test_empty_zero_ff_short_wrong_id_factory_uses_known_fallback(self):
        for data in (b'', b'\0' * 7680, b'\xff' * 7680, b'\x92\x79', b'\x90\x79' + b'\0' * 7678):
            with self.subTest(data=data[:4]):
                self.factory.write_bytes(data)
                result = self.run_boot()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.output.read_bytes(), self.data)
                self.assertIn('BE5040-fallback', result.stdout)

    def test_missing_factory_uses_fallback(self):
        self.assertEqual(self.run_boot().returncode, 0)
        self.assertEqual(self.output.read_bytes(), self.data)

    def test_stale_invalid_output_is_rebuilt(self):
        self.output.write_bytes(b'\0' * 7680)
        self.assertEqual(self.run_boot().returncode, 0)
        self.assertEqual(self.output.read_bytes(), self.data)

    def test_invalid_fallback_fails_without_installing_invalid_data(self):
        self.fallback.write_bytes(b'\0' * 7680)
        self.assertNotEqual(self.run_boot().returncode, 0)
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob('e2p.new.*')))


if __name__ == '__main__':
    unittest.main()
