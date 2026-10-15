"""Start a frozen app twice with synthetic data in an isolated user profile."""
import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--qt-platform', choices=('offscreen', 'xcb'), default='offscreen')
    args = parser.parse_args()
    executable = args.exe.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='aurora-frozen-profile-') as temporary:
        profile = Path(temporary)
        env = dict(os.environ, APPDATA=str(profile), XDG_DATA_HOME=str(profile),
                   QT_QPA_PLATFORM=args.qt_platform, AURORA_AUTOFILL_SMOKE_TEST='1')
        options = dict(env=env, cwd=profile, stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=25)
        if sys.platform == 'win32':
            options['creationflags'] = subprocess.CREATE_NO_WINDOW

        def launch():
            result = subprocess.run([str(executable)], **options)
            if result.returncode:
                sys.stderr.write(result.stderr.decode('utf-8', errors='replace'))
                raise SystemExit(f'Aplicativo compilado terminou com codigo {result.returncode}')

        launch()
        database = profile / 'AutoFillStudio' / 'snippets.sqlite3'
        if not database.is_file():
            raise SystemExit('Banco nao foi criado no perfil temporario esperado.')
        with closing(sqlite3.connect(database)) as connection, connection:
            folder = connection.execute("INSERT INTO folders(name) VALUES ('CI preservation')").lastrowid
            connection.execute('INSERT INTO snippets(folder_id,title,shortcut,content,rich_content) '
                               'VALUES (?,?,?,?,?)', (folder, 'CI preservation', '/cipreserve',
                                                     'Synthetic preserved data', ''))
        launch()
        with closing(sqlite3.connect(database)) as connection, connection:
            value = connection.execute('SELECT content FROM snippets WHERE shortcut=?',
                                       ('/cipreserve',)).fetchone()
            if value != ('Synthetic preserved data',):
                raise SystemExit('Dados sinteticos nao foram preservados na segunda inicializacao.')
    print('Frozen smoke passed: two starts; isolated profile; existing synthetic data preserved.')


if __name__ == '__main__':
    main()
