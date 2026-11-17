#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""发布前检查实际 H5000M 镜像、启动参数、EEPROM 配套、Samba4 排除。不能替代实机启动。"""
import argparse
import hashlib
import struct
import zlib
from pathlib import Path
import subprocess
import tarfile
import tempfile

FALLBACK = 'lib/firmware/MT7991_MT7976_EEPROM_BE5040_iPAiLNA.bin'


def run(*args):
    return subprocess.check_output(args, stderr=subprocess.PIPE)


def verify(path):
    with tempfile.TemporaryDirectory(prefix='h5000m-image-') as directory:
        work = Path(directory)
        with tarfile.open(path, 'r:') as image:
            members = image.getmembers()
            files = {}
            for kind in ('CONTROL', 'kernel', 'root'):
                matching = [m for m in members if m.isfile() and m.name.endswith('/' + kind)]
                if len(matching) != 1:
                    raise ValueError(f'{path}: 缺少唯一的 {kind}')
                target = work / kind
                with image.extractfile(matching[0]) as source, target.open('wb') as out:
                    import shutil
                    shutil.copyfileobj(source, out)
                files[kind] = target
        if files['CONTROL'].read_text().strip() != 'BOARD=hiveton_h5000m':
            raise ValueError('CONTROL 机型不匹配')
        fit = files['kernel']
        if run('fdtget', '-t', 's', str(fit), '/images/kernel-1', 'arch').strip() != b'arm64':
            raise ValueError('内核架构不是 arm64')
        if run('fdtget', '-t', 'x', str(fit), '/images/kernel-1', 'load').strip() != b'40000000':
            raise ValueError('Linux 6.12 H5000M 内核加载地址发生变化')
        for index, node in enumerate(('kernel-1', 'fdt-1')):
            payload = work / f'payload-{index}'
            run('dumpimage', '-T', 'flat_dt', '-p', str(index), '-o', str(payload), str(fit))
            content = payload.read_bytes()
            for child in run('fdtget', '-l', str(fit), '/images/' + node).decode().split():
                if not child.startswith('hash'):
                    continue
                hash_path = '/images/' + node + '/' + child
                algorithm = run('fdtget', '-t', 's', str(fit), hash_path, 'algo').decode().strip()
                expected = bytes(int(b, 16) for b in run('fdtget', '-t', 'bx', str(fit), hash_path, 'value').split())
                actual = struct.pack('>I', zlib.crc32(content)) if algorithm == 'crc32' else hashlib.new(algorithm, content).digest()
                if expected != actual:
                    raise ValueError(f'FIT {node} 的 {algorithm} 校验失败')
        run('dumpimage', '-T', 'flat_dt', '-p', '1', '-o', str(work / 'board.dtb'), str(fit))
        board = work / 'board.dtb'
        if b'hiveton,h5000m' not in run('fdtget', '-t', 's', str(board), '/', 'compatible').split():
            raise ValueError('设备树机型不匹配')
        args = run('fdtget', '-t', 's', str(board), '/chosen', 'bootargs').decode()
        for required in ('console=ttyS0,115200n8', 'root=PARTLABEL=rootfs', 'rootwait'):
            if required not in args:
                raise ValueError(f'缺少启动参数 {required}')
        cat = lambda file: run('unsquashfs', '-cat', str(files['root']), file)
        installed = cat('lib/apk/db/installed').decode()
        packages = [line[2:] for line in installed.splitlines() if line.startswith('P:')]
        if any('samba4' in name for name in packages):
            raise ValueError('固件仍包含 Samba4')
        fallback = cat(FALLBACK)
        if len(fallback) != 7680 or fallback[:2] != b'\x92\x79':
            raise ValueError('缺少有效的 BE5040 备用 EEPROM')
        profile = cat('etc/wireless/l1profile.dat').decode()
        for setting in ('INDEX0_profile_path=/etc/wireless/mediatek/mt7992.5040.1.dat',
                        'INDEX0_EEPROM_size=0x1e00', 'INDEX0_EEPROM_def_bin_path=/' + FALLBACK):
            if setting not in profile:
                raise ValueError(f'L1 profile 不匹配：{setting}')
        script = cat('etc/init.d/wifi_e2p')
        expected = (Path(__file__).resolve().parent / 'files/h5000m-wifi-e2p.init').read_bytes()
        if script != expected:
            raise ValueError('H5000M EEPROM 启动脚本未打入实际镜像')
        listing = run('unsquashfs', '-ll', str(files['root'])).decode()
        if 'squashfs-root/etc/rc.d/S07wifi_e2p -> ../init.d/wifi_e2p' not in listing:
            raise ValueError('EEPROM 初始化未排在 S10boot 前')
    with path.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    print(f'PASS {path.name}: H5000M FIT/eMMC boot arguments, BE5040 EEPROM/startup, no Samba4; SHA256={digest}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--images', type=Path, required=True)
    args = parser.parse_args()
    images = sorted(args.images.rglob('*hiveton_h5000m-squashfs-sysupgrade.bin'))
    if len(images) != 1:
        parser.error(f'需要唯一 H5000M squashfs sysupgrade，找到 {len(images)} 个')
    verify(images[0])


if __name__ == '__main__':
    main()
