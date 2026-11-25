"""Build Flutter only when the web sources changed; runtime startup needs no SDK."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
STAMP = ROOT / '.local' / 'web-source.sha256'


def source_hash():
    files = [ROOT/'pubspec.yaml',ROOT/'pubspec.lock']
    files += sorted((ROOT/'lib').rglob('*.dart'))
    files += sorted(p for p in (ROOT/'web').rglob('*') if p.is_file())
    checksum = hashlib.sha256()
    checksum.update(Path(__file__).read_bytes())
    for file in files:
        checksum.update(str(file.relative_to(ROOT)).encode())
        checksum.update(file.read_bytes())
    return checksum.hexdigest()


def build(force=False):
    wanted=source_hash()
    if not force and (ROOT/'build/web/index.html').is_file() and STAMP.is_file() and STAMP.read_text().strip()==wanted:
        return
    flutter=os.getenv('FLUTTER_BIN') or shutil.which('flutter')
    if not flutter:
        raise SystemExit('Prima compilazione: installa Flutter 3.47.6 oppure imposta FLUTTER_BIN.')
    subprocess.run([flutter,'pub','get'],cwd=ROOT,check=True)
    # No URL compiled in: the browser calls the API on the same origin.
    subprocess.run([flutter,'build','web','--release','--no-pub','--no-web-resources-cdn'],cwd=ROOT,check=True)
    STAMP.parent.mkdir(parents=True,exist_ok=True)
    STAMP.write_text(wanted+'\n')


if __name__=='__main__':
    build()
