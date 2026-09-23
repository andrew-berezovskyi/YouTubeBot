"""Locate supported runtimes, including Windows installs outside stale PATH."""
import os
import re
import shutil
import subprocess
from pathlib import Path
from functools import lru_cache

@lru_cache(maxsize=1)
def available_runtime():
    for name,minimum in (('deno',(2,3,0)),('node',(22,0,0))):
        candidates=[shutil.which(name)]
        if name=='deno':
            candidates += [str(Path.home()/'.deno/bin/deno.exe')]
            local=os.environ.get('LOCALAPPDATA')
            if local:candidates += [str(Path(local)/'Microsoft/WinGet/Links/deno.exe')]
        else:
            program=os.environ.get('ProgramFiles')
            if program:candidates += [str(Path(program)/'nodejs/node.exe')]
        for path in candidates:
            if not path or not Path(path).is_file():continue
            try:
                result=subprocess.run([path,'--version'],capture_output=True,text=True,timeout=10,check=True)
                match=re.search(r'(\d+)\.(\d+)\.(\d+)',result.stdout)
                if match and tuple(map(int,match.groups()))>=minimum:return name,path,result.stdout.splitlines()[0]
            except (OSError,subprocess.SubprocessError):continue
    return None

def runtime_args():
    found=available_runtime()
    return ['--js-runtimes',f'{found[0]}:{found[1]}'] if found else []

def require_runtime():
    found=available_runtime()
    if not found:raise RuntimeError('Install Deno >=2.3: winget install --id DenoLand.Deno -e; then restart VS Code')
    return found[2]
