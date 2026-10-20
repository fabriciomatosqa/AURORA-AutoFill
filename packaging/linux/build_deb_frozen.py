#!/usr/bin/env python3
"""Empacota o diretório PyInstaller/Linux como pacote .deb instalável."""
from pathlib import Path
import argparse
import os
import shutil
import subprocess
import tempfile


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--dist', type=Path, default=Path('dist/AURORA AutoFill'))
    p.add_argument('--out', type=Path, default=Path('AURORA-AutoFill-v0.5.3-Linux-amd64.deb'))
    args = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    executable = args.dist / 'AURORA AutoFill'
    if not executable.is_file():
        raise SystemExit(f'Não encontrei o aplicativo PyInstaller: {executable}')
    with tempfile.TemporaryDirectory(prefix='aurora-deb-') as temp:
        stage = Path(temp) / 'package'
        for folder in ['DEBIAN', 'opt/aurora-autofill', 'usr/bin',
                       'usr/share/applications', 'usr/share/icons/hicolor/256x256/apps']:
            (stage / folder).mkdir(parents=True, exist_ok=True)
        shutil.copytree(args.dist, stage / 'opt/aurora-autofill', dirs_exist_ok=True)
        shutil.copy2(root/'assets/aurora_icon_256.png', stage/'usr/share/icons/hicolor/256x256/apps/aurora-autofill.png')
        (stage/'DEBIAN/control').write_text('''Package: aurora-autofill
Version: 0.5.3
Section: utils
Priority: optional
Architecture: amd64
Maintainer: Fabricio Matos
Homepage: https://github.com/fabriciomatosqa/AURORA-AutoFill
Depends: libxcb-cursor0, libxkbcommon-x11-0
Description: Expansor de texto AURORA AutoFill
 Aplicativo desktop com atalhos de texto e pastas, desenvolvido por Fabricio Matos.
''', encoding='utf-8')
        launcher = stage/'usr/bin/aurora-autofill'
        launcher.write_text('#!/bin/sh\nexec "/opt/aurora-autofill/AURORA AutoFill" "$@"\n',encoding='utf-8')
        launcher.chmod(0o755)
        desktop = stage/'usr/share/applications/aurora-autofill.desktop'
        desktop.write_text('''[Desktop Entry]
Type=Application
Name=AURORA AutoFill
Comment=Expansão inteligente de textos
Exec=/usr/bin/aurora-autofill
Icon=aurora-autofill
Terminal=false
Categories=Utility;Office;
StartupWMClass=AURORA AutoFill
''', encoding='utf-8')
        args.out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['dpkg-deb', '--build', '--root-owner-group', str(stage), str(args.out)], check=True)
        print(f'Pacote criado: {args.out}')


if __name__ == '__main__':
    main()