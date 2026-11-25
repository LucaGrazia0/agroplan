"""Sign a Release APK locally; the persistent private key never enters CI."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--badging', type=Path, required=True)
    parser.add_argument('--java', type=Path, required=True)
    parser.add_argument('--apksigner', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--build', required=True)
    args = parser.parse_args()
    metadata = args.badging.read_text()
    assert "package: name='it.lucagrazia.agroplan'" in metadata
    assert f"versionName='{args.version}'" in metadata
    assert f"versionCode='{args.build}'" in metadata
    assert "native-code: 'arm64-v8a'" in metadata
    assert 'android.permission.INTERNET' in metadata
    assert 'application-debuggable' not in metadata
    with zipfile.ZipFile(args.input) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert 'lib/arm64-v8a/libapp.so' in names
        assert 'lib/arm64-v8a/libflutter.so' in names
        assert all('..' not in Path(n).parts and not n.startswith('/') for n in names)
        assert not any(Path(n).suffix.lower() in {'.p12','.p8','.key','.pem','.jks','.keystore','.sqlite','.sqlite3','.db'} or Path(n).name.startswith('.env') for n in names)
    directory = ROOT / '.local/android-signing'
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    key, cert = directory / 'agroplan.pk8', directory / 'agroplan-cert.pem'
    if key.exists() != cert.exists():
        raise SystemExit('Materiale di firma incompleto: nessuna chiave sostituita.')
    if not key.exists():
        old_mask = os.umask(0o077)
        try:
            pem = directory / 'agroplan-private.pem'
            subprocess.run(['openssl','genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:3072','-out',str(pem)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            subprocess.run(['openssl','req','-new','-x509','-sha256','-key',str(pem),'-out',str(cert),'-days','10000','-subj','/CN=AgroPlan/O=AgroPlan'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            subprocess.run(['openssl','pkcs8','-topk8','-inform','PEM','-outform','DER','-in',str(pem),'-out',str(key),'-nocrypt'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            pem.unlink()
        finally:
            os.umask(old_mask)
    key.chmod(0o600); cert.chmod(0o600)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run([str(args.java),'-jar',str(args.apksigner),'sign','--key',str(key),'--cert',str(cert),'--out',str(args.output),str(args.input)],check=True)
    verification = subprocess.check_output([str(args.java),'-jar',str(args.apksigner),'verify','--verbose','--print-certs',str(args.output)],text=True)
    assert 'Verified using v2 scheme (APK Signature Scheme v2): true' in verification
    public_cert = subprocess.check_output(['openssl','x509','-in',str(cert),'-outform','DER'])
    fingerprint = hashlib.sha256(public_cert).hexdigest()
    assert f'Signer #1 certificate SHA-256 digest: {fingerprint}' in verification
    # Signing must leave application payload and native-library alignment intact.
    with zipfile.ZipFile(args.input) as before, zipfile.ZipFile(args.output) as after:
        assert after.testzip() is None
        for name in before.namelist():
            if not name.startswith('META-INF/'):
                assert before.read(name)==after.read(name)
        with args.output.open('rb') as raw:
            for item in after.infolist():
                if item.filename.startswith('lib/') and item.filename.endswith('.so') and item.compress_type==zipfile.ZIP_STORED:
                    raw.seek(item.header_offset+26)
                    fields=raw.read(4)
                    offset=item.header_offset+30+int.from_bytes(fields[:2],'little')+int.from_bytes(fields[2:],'little')
                    assert offset % 16384 == 0, 'Libreria nativa non allineata a 16 KiB'
    report = dict(file=args.output.name,version=args.version,build=args.build,architectures=['arm64-v8a'],signed=True,
                  application_id='it.lucagrazia.agroplan',minimum_android_api=re.search(r"sdkVersion:'(\d+)'",metadata).group(1),
                  bytes=args.output.stat().st_size,size_mib=round(args.output.stat().st_size/1024**2,2),
                  sha256=hashlib.sha256(args.output.read_bytes()).hexdigest(),certificate_sha256=fingerprint,
                  server='https://agroplan-backend.onrender.com')
    args.output.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('file','version','build','bytes','size_mib','minimum_android_api')}))


if __name__ == '__main__':
    main()
