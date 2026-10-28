"""Validate the PyInstaller directory before creating distributable packages."""
import argparse
import hashlib
import json
from pathlib import Path

ASSETS = ('aurora_banner.jpg', 'aurora_banner_day.png', 'aurora_icon.ico', 'aurora_icon.png',
          'aurora_icon_256.png', 'command_click.wav', 'AUDIO-LICENSE.txt',
          'checkmark.svg', 'chevron_down.svg')
ASSETS += ('emoji/fluent-3d.png','emoji/fluent-3d.json','emoji/ATTRIBUTION.md',
           'emoji/LICENSE-Fluent.txt')
ASSETS += tuple('icons/' + name + '.svg' for name in (
    'settings', 'home', 'save', 'trash', 'plus', 'minus', 'export', 'import',
    'undo', 'folder', 'play', 'pause', 'volume', 'update', 'backup', 'restore',
    'back', 'check', 'close', 'bolt', 'bold', 'italic', 'underline',
    'font-increase', 'font-decrease', 'align-left', 'align-center', 'align-right',
    'align-justify', 'list-bullets', 'list-numbered', 'list-multilevel', 'indent-less',
    'indent-more', 'line-spacing', 'paragraph-shading', 'paragraph-border', 'sort-text',
    'paragraph-settings'))


def verify_bundle(dist, platform, source_root=None):
    dist = Path(dist)
    source = Path(source_root) if source_root else Path(__file__).resolve().parents[1]
    executable = dist / ('AURORA AutoFill.exe' if platform == 'windows' else 'AURORA AutoFill')
    if not executable.is_file():
        raise ValueError('Executavel ausente no pacote.')
    internal = dist / '_internal'
    hashes = {}
    for name in ASSETS:
        resource = internal / 'assets' / name
        if not resource.is_file():
            raise ValueError(f'Recurso ausente: assets/{name}')
        digest = hashlib.sha256(resource.read_bytes()).hexdigest()
        if digest != hashlib.sha256((source / 'assets' / name).read_bytes()).hexdigest():
            raise ValueError(f'Recurso diferente do original: assets/{name}')
        hashes['assets/' + name] = digest
    plugin = 'qwindows.dll' if platform == 'windows' else 'libqxcb.so'
    if not any(internal.glob('PySide6/**/plugins/platforms/' + plugin)):
        raise ValueError('Plugin Qt de plataforma ausente: ' + plugin)
    if platform == 'windows':
        for name in ('accessibility_worker.ps1', 'accessibility_worker.cs', 'word_worker.ps1', 'word_worker.cs'):
            worker = internal / 'app' / name
            expected = source / 'app' / name
            if not worker.is_file() or worker.read_bytes() != expected.read_bytes():
                raise ValueError('Worker UIA ausente ou diferente em _internal/app/' + name)
            hashes['app/' + name] = hashlib.sha256(worker.read_bytes()).hexdigest()
    for path in dist.rglob('*'):
        relative = path.relative_to(dist)
        names = {part.lower() for part in relative.parts}
        name = path.name.lower()
        if names & {'qa', 'tests', '__pycache__', '.git', '.venv', 'venv', '.aws', '.ssh'}:
            raise ValueError('Diretorio local indevido no pacote: ' + str(relative))
        if not path.is_file():
            continue
        if (path.suffix.lower() in {'.log', '.jsonl', '.sqlite', '.sqlite3', '.db', '.pfx', '.p12'}
                or '.sqlite' in name or name.endswith(('.db-wal', '.db-shm', '.db-journal'))
                or name == '.env' or name.startswith('.env.')
                or name in {'credentials.json', 'id_rsa', 'id_ed25519', '.git-credentials', '.netrc'}):
            raise ValueError('Arquivo local ou sensivel indevido: ' + str(relative))
        if path.suffix.lower() in {'.pem', '.key'}:
            if b'PRIVATE KEY-----' in path.read_bytes():
                raise ValueError('Chave privada indevida no pacote: ' + str(relative))
    return dict(platform=platform, executable=executable.name, resources_sha256=hashes,
                qt_platform_plugin=plugin, local_data_scan='passed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, default=Path('dist/AURORA AutoFill'))
    parser.add_argument('--platform', choices=('windows', 'linux'), required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = verify_bundle(args.dist, args.platform)
    output = json.dumps(result, indent=2)
    if args.report:
        args.report.write_text(output, encoding='utf-8')
    print(output)


if __name__ == '__main__':
    main()
