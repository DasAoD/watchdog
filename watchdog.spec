# -*- mode: python ; coding: utf-8 -*-

import glob
import os

# block_cipher = None

# Daten-Dateien vorbereiten
datas_to_add = []
# Icon hinzufügen
datas_to_add.append((os.path.join('icon', 'watchdog.ico'), 'icon'))
# Sprachdateien hinzufügen
for f_path in glob.glob(os.path.join('lang', '*.json')):
    datas_to_add.append((f_path, 'lang'))

# --- Analysis Block ---
a = Analysis(
    ['watchdog.py'],
    pathex=[],
    binaries=[],
    datas=datas_to_add,  # <<< HIER DIREKT ÜBERGEBEN
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False
)

# --- PYZ Block ---
pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=None
)

# --- EXE Block ---
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles, # Wichtig, diesen hier zu haben
    a.datas,    # a.datas wird hier immer noch übergeben, da es Teil des Analysis-Objekts ist
    [],
    name='Watchdog',
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
    icon=os.path.join('icon', 'watchdog.ico'),
    version='version.txt'
)