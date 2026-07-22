from __future__ import annotations
import os, shutil, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
print('VA Claim Builder 4.0 - Increment 13 installer')
print('Python:',sys.version.split()[0])
if sys.version_info < (3,10): raise SystemExit('Python 3.10+ is required.')
subprocess.check_call([sys.executable,'-m','pip','install','-r',str(ROOT/'requirements.txt')])
env=ROOT/'.env'
if not env.exists(): shutil.copy2(ROOT/'.env.example',env); print('Created .env from template.')
(ROOT/'data').mkdir(exist_ok=True)
print('Tesseract:',shutil.which('tesseract') or 'not found (optional; install for scanned PDFs)')
print('Installation complete. Run scripts/run_mac_linux.sh or scripts/run_windows.bat.')
