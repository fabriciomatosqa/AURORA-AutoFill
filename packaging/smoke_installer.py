"""Exercise the real Windows installer on a disposable GitHub-hosted runner."""
import argparse
from contextlib import closing
import hashlib
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time


UNINSTALL_KEY = ('Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\'
                 r'{6C34F9C8-9F89-4D4B-B894-0F33A4A0D379}_is1')


def wait_for_profile(database, seconds=25):
    """The automatically reopened app uses its existing isolated smoke mode."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not database.is_file():
            time.sleep(0.2)
            continue
        try:
            with closing(sqlite3.connect(database, timeout=1)) as connection:
                if connection.execute('SELECT count(*) FROM folders').fetchone():
                    return
        except sqlite3.Error:
            pass
        time.sleep(0.2)
    raise RuntimeError('O instalador nao reabriu o app no perfil temporario.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installer', required=True, type=Path)
    args = parser.parse_args()
    # This test intentionally creates/uninstalls the real AppId. Never run it
    # on an end-user profile or a persistent self-hosted Windows runner.
    if (sys.platform != 'win32' or os.environ.get('GITHUB_ACTIONS') != 'true'
            or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted'):
        parser.error('Este teste somente pode rodar em um runner Windows descartavel do GitHub.')
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY):
            raise SystemExit('Ja existe uma instalacao do AURORA neste perfil; teste recusado.')
    except FileNotFoundError:
        pass

    installer = args.installer.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='aurora-installer-',
                                     dir=os.environ.get('RUNNER_TEMP'),
                                     ignore_cleanup_errors=True) as temporary:
        root = Path(temporary)
        target = root / 'application with spaces'
        profile = root / 'profile'
        profile.mkdir()
        setup_temporary = root / 'setup-temporary'
        setup_temporary.mkdir()
        env = dict(os.environ, APPDATA=str(profile), QT_QPA_PLATFORM='offscreen',
                   AURORA_AUTOFILL_SMOKE_TEST='1', TEMP=str(setup_temporary),
                   TMP=str(setup_temporary))
        database = profile / 'AutoFillStudio' / 'snippets.sqlite3'

        def read_log(log):
            content = log.read_bytes()
            encoding = 'utf-16' if content.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig'
            return content.decode(encoding, errors='replace')

        def dump_logs():
            for log in [*root.glob('*.log'), *setup_temporary.glob('Setup Log*.txt')]:
                print(f'Installer diagnostic log: {log.name}', flush=True)
                print(read_log(log)[-14000:], flush=True)

        def run(parameters, expected=(0,)):
            print(f'Installer smoke: starting {parameters}', flush=True)
            process = subprocess.Popen([str(installer), *parameters], env=env,
                                       cwd=root, stdin=subprocess.DEVNULL,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                returncode = process.wait(timeout=150)
            except subprocess.TimeoutExpired:
                dump_logs()
                # Only the installer process tree launched by this disposable
                # test is stopped, so it cannot leave a hidden wizard behind.
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                               check=False, timeout=20,
                               creationflags=subprocess.CREATE_NO_WINDOW)
                process.wait(timeout=10)
                raise
            print(f'Installer smoke: installer exit={returncode}', flush=True)
            if returncode not in expected:
                dump_logs()
                raise RuntimeError(f'Instalador terminou com codigo {returncode}.')

        quiet = ['/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-',
                 '/NORESTARTAPPLICATIONS']
        uninstaller = target / 'unins000.exe'
        try:
            run([*quiet, f'/DIR={target}', '/NOICONS', '/TASKS=',
                 f'/LOG={root / "first.log"}'])
            executable = target / 'AURORA AutoFill.exe'
            if not executable.is_file() or not uninstaller.is_file():
                raise RuntimeError('A primeira instalacao nao criou os executaveis esperados.')
            if database.exists():
                raise RuntimeError('Instalacao silenciosa comum abriu o app sem ser uma atualizacao.')
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
                installed_path = winreg.QueryValueEx(key, 'InstallLocation')[0]
            if Path(installed_path).resolve() != target.resolve():
                raise RuntimeError('Diretorio registrado difere do destino temporario.')
            print('Installer smoke: first installation passed; no automatic start.', flush=True)

            provenance = target / 'SOURCE-COMMIT.txt'
            expected_provenance = hashlib.sha256(provenance.read_bytes()).digest()
            provenance.write_text('synthetic file to replace', encoding='utf-8')
            run([*quiet, '/AURORAUPDATE=1', f'/LOG={root / "update.log"}'])
            wait_for_profile(database)
            if hashlib.sha256(provenance.read_bytes()).digest() != expected_provenance:
                raise RuntimeError('Atualizacao nao substituiu os arquivos no diretorio existente.')
            update_log = read_log(root / 'update.log')
            if 'AURORA: in-app update; silent=1' not in update_log:
                raise RuntimeError('Atualizacao nao confirmou execucao sem assistente.')
            with closing(sqlite3.connect(database)) as connection, connection:
                connection.execute("INSERT INTO folders(name) VALUES ('CI preserved update')")
            print('Installer smoke: explicit silent update and automatic reopen passed.', flush=True)
            # Wait for the reopened smoke application to finish before the
            # next installer replaces its executable (no process force-kill).
            time.sleep(2)

            provenance.write_text('second synthetic file to replace', encoding='utf-8')
            legacy_profile = root / 'legacy-profile'
            legacy_profile.mkdir()
            env['APPDATA'] = str(legacy_profile)
            # Exact invocation used by 0.6.1-161026. InitializeSetup hands off
            # to its silent child and aborts the outer bootstrap with code 1.
            run(['/NORESTART'], expected=(1,))
            wait_for_profile(legacy_profile / 'AutoFillStudio' / 'snippets.sqlite3')
            legacy_logs = '\n'.join(read_log(log) for log in setup_temporary.glob('Setup Log*.txt'))
            if ('AURORA: legacy updater detected; handing off without a wizard.' not in legacy_logs
                    or 'AURORA: silent update finished; exit=0' not in legacy_logs):
                dump_logs()
                raise RuntimeError('A transicao legada nao confirmou instalacao silenciosa concluida.')
            if hashlib.sha256(provenance.read_bytes()).digest() != expected_provenance:
                raise RuntimeError('A transicao do atualizador antigo nao substituiu os arquivos.')
            with closing(sqlite3.connect(database)) as connection:
                if not connection.execute(
                        "SELECT 1 FROM folders WHERE name='CI preserved update'").fetchone():
                    raise RuntimeError('Atualizacao nao preservou o perfil sintetico.')
            print('Installer smoke: exact legacy invocation, silent handoff and data preservation passed.',
                  flush=True)
            time.sleep(2)
        finally:
            if uninstaller.is_file():
                result = subprocess.run([str(uninstaller), '/VERYSILENT',
                                         '/SUPPRESSMSGBOXES', '/NORESTART'],
                                        env=env, cwd=root, timeout=90,
                                        creationflags=subprocess.CREATE_NO_WINDOW)
                if result.returncode:
                    raise RuntimeError('Nao foi possivel limpar a instalacao temporaria do CI.')
    print('Installer smoke passed: first install; silent update/reopen; legacy handoff; data preserved.')


if __name__ == '__main__':
    main()
