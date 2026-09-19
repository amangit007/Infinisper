# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs

block_cipher = None

datas = [
    ('assets', 'assets'),
]
datas += collect_data_files('sherpa_onnx')
datas += collect_data_files('litellm')

binaries = []
binaries += collect_dynamic_libs('sherpa_onnx')
binaries += collect_dynamic_libs('onnxruntime')
binaries += collect_dynamic_libs('ctranslate2')
binaries += collect_dynamic_libs('sounddevice')

hiddenimports = [
    'sounddevice',
    '_cffi_backend',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtNetwork',
    'PySide6.QtSvg',
    'keyring.backends.Windows',
    'sherpa_onnx',
    'onnxruntime',
    'ctranslate2',
    'faster_whisper',
    'litellm',
]
hiddenimports += collect_submodules('keyring')
hiddenimports += collect_submodules('dictation')
hiddenimports += collect_submodules('asr')
hiddenimports += collect_submodules('audio')
hiddenimports += collect_submodules('cleanup')
hiddenimports += collect_submodules('history')
hiddenimports += collect_submodules('ui')
hiddenimports += collect_submodules('utils')

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Infinisper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/infinisper.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Infinisper',
)
