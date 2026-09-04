# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files


ttkbootstrap_data = collect_data_files('ttkbootstrap')
ttkbootstrap_assets = Path(__import__('ttkbootstrap').__file__).parent / 'assets'
ttkbootstrap_data.append((str(ttkbootstrap_assets), 'ttkbootstrap/assets'))

a = Analysis(
    ['recon_app.py'],
    pathex=[],
    binaries=[],
    datas=ttkbootstrap_data,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='recon_app',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
