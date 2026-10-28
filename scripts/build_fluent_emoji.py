"""Build the offline Fluent 3D atlas from the pinned Microsoft source files.

Run with Pillow installed. The app never downloads assets at runtime.
"""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import tempfile
from urllib.parse import quote
from urllib.request import urlopen

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT/'assets/emoji/fluent-3d.json'


def main():
    data = json.loads(MANIFEST.read_text(encoding='utf-8'))
    revision = data['source_revision']
    cache = Path(tempfile.gettempdir())/'aurora-fluent-source'/revision
    cache.mkdir(parents=True,exist_ok=True)
    def download(item):
        emoji, record = item
        source = record['source']
        if not source.startswith('assets/') or not source.endswith('.png') or '..' in source:
            raise ValueError('Invalid Fluent source: '+source)
        cached = cache/(sha256(source.encode()).hexdigest()+'.png')
        if not cached.is_file():
            url = 'https://raw.githubusercontent.com/microsoft/fluentui-emoji/'+revision+'/'+quote(source)
            last_error = None
            for _ in range(3):
                try:
                    payload = urlopen(url,timeout=30).read()
                    cached.write_bytes(payload)
                    break
                except OSError as error:
                    last_error = error
            else:
                raise last_error
        payload = cached.read_bytes()
        digest = sha256(payload).hexdigest()
        if record.get('sha256') and record['sha256'] != digest:
            raise ValueError('Fluent source checksum changed: '+source)
        image = Image.open(BytesIO(payload)).convert('RGBA')
        image.thumbnail((96,96),Image.Resampling.LANCZOS)
        tile = Image.new('RGBA',(96,96))
        tile.paste(image,((96-image.width)//2,(96-image.height)//2))
        return emoji, digest, tile
    entries = sorted(data['emoji'].items())
    columns = 18
    atlas = Image.new('RGBA',(columns*96,((len(entries)+columns-1)//columns)*96))
    with ThreadPoolExecutor(max_workers=12) as pool:
        for index,(emoji,digest,tile) in enumerate(pool.map(download,entries)):
            x,y = index%columns*96,index//columns*96
            atlas.paste(tile,(x,y))
            data['emoji'][emoji]['rect'] = [x,y,96,96]
            data['emoji'][emoji]['sha256'] = digest
    target = MANIFEST.with_name(data['atlas'])
    atlas.save(target,optimize=True,compress_level=9)
    data['atlas_sha256'] = sha256(target.read_bytes()).hexdigest()
    MANIFEST.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Fluent 3D: {len(entries)} emojis; atlas {target.stat().st_size} bytes; source {revision}.')


if __name__ == '__main__':
    main()
