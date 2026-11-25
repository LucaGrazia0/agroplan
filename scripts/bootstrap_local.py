"""Prepare an isolated, reproducible local runtime and start AgroPlan."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import venv

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/'.local/runtime'
PYTHON=RUNTIME/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
LOCK=ROOT/'backend/requirements-lock.txt'


def main():
    if sys.version_info < (3,12):
        raise SystemExit('Serve Python 3.12 o successivo.')
    if not PYTHON.is_file():
        venv.EnvBuilder(with_pip=True).create(RUNTIME)
    wanted=hashlib.sha256(LOCK.read_bytes()).hexdigest()
    stamp=RUNTIME/'.requirements.sha256'
    if not stamp.is_file() or stamp.read_text().strip()!=wanted:
        subprocess.run([str(PYTHON),'-m','pip','install','--disable-pip-version-check','--cache-dir',str(ROOT/'.local/pip-cache'),'-r',str(LOCK)],check=True)
        stamp.write_text(wanted+'\n')
    from build_web import build
    build()
    os.execv(str(PYTHON),[str(PYTHON),str(ROOT/'scripts/run_local.py'),*sys.argv[1:]])


if __name__=='__main__':
    main()
