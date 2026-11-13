"""Build a compact, unsigned device IPA for signing with a sideloading tool."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-url', default='', help='Optional HTTPS backend; otherwise selected inside the app')
    args = parser.parse_args()
    if sys.platform != 'darwin' or shutil.which('xcodebuild') is None:
        parser.error('Serve macOS con Xcode completo. In alternativa usa il workflow iOS su GitHub.')
    if args.api_url:
        from urllib.parse import urlsplit
        url = urlsplit(args.api_url)
        if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
            parser.error('--api-url deve essere un URL HTTPS senza credenziali, query o frammenti.')
    flutter = os.getenv('FLUTTER_BIN') or shutil.which('flutter')
    if not flutter:
        parser.error('Installa Flutter 3.47.6 oppure imposta FLUTTER_BIN.')
    subprocess.run([flutter, 'pub', 'get'], cwd=ROOT, check=True)
    command = [flutter, 'build', 'ios', '--release', '--no-pub', '--no-codesign',
               '--tree-shake-icons', '--split-debug-info=build/ios-symbols']
    if args.api_url:
        command.append('--dart-define=AGROPLAN_API_URL=' + args.api_url.rstrip('/'))
    subprocess.run(command, cwd=ROOT, check=True)
    app = ROOT / 'build/ios/iphoneos/Runner.app'
    with (app / 'Info.plist').open('rb') as file:
        info = plistlib.load(file)
    if info.get('DTPlatformName') != 'iphoneos':
        raise SystemExit('La build non è destinata a un iPhone/iPad fisico.')
    executable = app / info['CFBundleExecutable']
    architectures = subprocess.check_output(['xcrun', 'lipo', '-archs', str(executable)], text=True).split()
    if architectures != ['arm64']:
        raise SystemExit(f'Architetture inattese: {architectures}')
    output = ROOT / 'build/ios/ipa'
    output.mkdir(parents=True, exist_ok=True)
    ipa = output / 'AgroPlan.ipa'
    temporary = ipa.with_suffix('.ipa.tmp')
    with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(app.rglob('*')):
            name = 'Payload/Runner.app/' + path.relative_to(app).as_posix()
            if path.is_symlink():
                entry = zipfile.ZipInfo(name)
                entry.create_system = 3
                entry.external_attr = path.lstat().st_mode << 16
                archive.writestr(entry, os.readlink(path))
            elif path.is_file():
                archive.write(path, name)
    with zipfile.ZipFile(temporary) as archive:
        if archive.testzip() is not None:
            raise SystemExit('Archivio IPA non valido.')
    temporary.replace(ipa)
    report = {
        'file': ipa.name, 'version': info['CFBundleShortVersionString'],
        'build': info['CFBundleVersion'], 'architectures': architectures,
        'signed': False, 'bytes': ipa.stat().st_size,
        'size_mib': round(ipa.stat().st_size / 1024**2, 2),
        'sha256': hashlib.sha256(ipa.read_bytes()).hexdigest(),
        'server': args.api_url or 'Da configurare nell’app',
    }
    (output / 'AgroPlan-build.json').write_text(json.dumps(report, indent=2) + '\n')
    (output / 'LEGGIMI.txt').write_text(
        'AgroPlan per iPhone/iPad — build Release arm64\n\n'
        'IPA non firmata: usare iLoader/AltStore o uno strumento equivalente per firmarla e installarla.\n'
        'Non è un pacchetto firmato per TestFlight o App Store.\n'
        'Al primo avvio configura un server AgroPlan HTTPS raggiungibile dal telefono.\n'
        'Il server Python e le credenziali dei provider non sono inclusi nell’app.\n'
        'localhost indica l’iPhone, non il Mac; il launcher locale sul Mac non è esposto alla rete.\n'
        'L’accesso senza password sul Mac resta disponibile come prima.\n'
    )
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
