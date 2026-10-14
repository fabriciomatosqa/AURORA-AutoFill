#!/usr/bin/env python3
"""Gera um DEB autoinstalável (offline) baseado em wheelhouse Linux amd64.

O Python e python3-venv são fornecidos pelo apt; PySide6, pynput e Xlib são
instalados em um venv do próprio usuário na primeira execução (sem rede).
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile


WHEEL_PATTERNS = (
    'shiboken6-*.whl',
    'pyside6_essentials-*.whl',
    'pynput-*.whl',
    'python_xlib-*.whl',
)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--wheels-qt',type=Path,required=True)
    parser.add_argument('--wheels-hotkeys',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix='aurora-bootstrap-') as d:
        stage=Path(d)/'pkg'
        dest=stage/'opt/aurora-autofill'
        for sub in ('DEBIAN','usr/bin','usr/share/applications','usr/share/icons/hicolor/256x256/apps'):
            (stage/sub).mkdir(parents=True,exist_ok=True)
        dest.mkdir(parents=True)
        for name in ('main.py','requirements.txt'):
            shutil.copy2(root/name,dest/name)
        for name in ('app','assets'):
            shutil.copytree(root/name,dest/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        wheelhouse=dest/'wheels'
        wheelhouse.mkdir()
        count=0
        for pattern in WHEEL_PATTERNS:
            matches=list(args.wheels_qt.glob(pattern))+list(args.wheels_hotkeys.glob(pattern))
            if len(matches)!=1:
                raise RuntimeError(f'Esperado exatamente 1 arquivo {pattern}; encontrei {matches}')
            shutil.copy2(matches[0], wheelhouse/matches[0].name)
            count+=1
        # Six is a 1-file pure Python dependency for pynput/python-xlib.
        import six
        vendor=dest/'vendor'
        vendor.mkdir()
        shutil.copy2(Path(six.__file__),vendor/'six.py')
        (dest/'run.sh').write_text('''#!/bin/sh
set -eu
APP_HOME="${AURORA_APP_HOME:-/opt/aurora-autofill}"
RUNTIME="${XDG_CACHE_HOME:-$HOME/.cache}/aurora-autofill/python-runtime-051"
if [ ! -e "$RUNTIME/.installed" ]; then
  mkdir -p "$(dirname "$RUNTIME")"
  python3 -m venv "$RUNTIME" || { echo "Instale python3-venv." >&2; exit 1; }
  "$RUNTIME/bin/python" -m pip install --disable-pip-version-check --no-index --no-deps --find-links "$APP_HOME/wheels" shiboken6 PySide6_Essentials pynput python-xlib || exit 1
  touch "$RUNTIME/.installed"
fi
cd "$APP_HOME"
export PYTHONPATH="$APP_HOME/vendor${PYTHONPATH:+:$PYTHONPATH}"
exec "$RUNTIME/bin/python" "$APP_HOME/main.py" "$@"
''',encoding='utf-8')
        (dest/'run.sh').chmod(0o755)
        launcher=stage/'usr/bin/aurora-autofill'
        launcher.write_text('#!/bin/sh\nexec /opt/aurora-autofill/run.sh "$@"\n',encoding='utf-8')
        launcher.chmod(0o755)
        shutil.copy2(root/'assets/aurora_icon_256.png',stage/'usr/share/icons/hicolor/256x256/apps/aurora-autofill.png')
        (stage/'usr/share/applications/aurora-autofill.desktop').write_text('''[Desktop Entry]
Type=Application
Name=AURORA AutoFill
Comment=Expansão inteligente de textos
Exec=/usr/bin/aurora-autofill
Icon=aurora-autofill
Terminal=false
Categories=Utility;Office;
StartupWMClass=AURORA AutoFill
''',encoding='utf-8')
        (stage/'DEBIAN/control').write_text('''Package: aurora-autofill-bootstrap
Version: 0.5.1
Section: utils
Priority: optional
Architecture: amd64
Maintainer: Fabricio Matos
Homepage: https://github.com/fabriciomatosqa/AURORA-AutoFill
Depends: python3 (>= 3.10), python3-venv, libxcb-cursor0, libxkbcommon-x11-0
Description: AURORA AutoFill (instalador de testes offline)
 Interface PySide6 para expansão de texto; bibliotecas Qt incluídas em wheels.
''',encoding='utf-8')
        args.out.parent.mkdir(parents=True,exist_ok=True)
        subprocess.run(['dpkg-deb','--build','--root-owner-group',str(stage),str(args.out)],check=True)
        print('Criado',args.out,'wheelhouse',count)


if __name__=='__main__':
    main()