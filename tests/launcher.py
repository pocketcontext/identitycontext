#!/usr/bin/env python3
"""Test the published package through a copied pinned launcher and empty home."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='identity-launcher-') as temporary:
    directory=Path(temporary);launcher=directory/'identitycontext';shutil.copy(ROOT/'skills/identitycontext/identitycontext',launcher);launcher.chmod(0o755)
    env={**os.environ,'HOME':str(directory/'home'),'XDG_STATE_HOME':str(directory/'state'),'UV_CACHE_DIR':str(directory/'uv-cache')};Path(env['HOME']).mkdir()
    result=subprocess.run([str(launcher),'--help'],cwd=directory,env=env,capture_output=True,text=True,timeout=120)
    assert result.returncode==0,result.stderr
    assert 'whoami' in result.stdout
    result=subprocess.run([str(launcher),'whoami','--email','synthetic@pocketcontext.com'],cwd=directory,env=env,capture_output=True,text=True,timeout=30)
    assert result.returncode==1 and 'No shared identity session' in result.stderr
    assert 'Traceback' not in result.stderr
print('PASS: copied launcher fetches published package and handles empty private state outside repository')
