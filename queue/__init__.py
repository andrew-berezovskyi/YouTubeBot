"""Keep legacy queue.manager while exposing Python's standard queue API.

The original project package shadows stdlib queue. Third-party HTTP/download
libraries still need Queue, Empty, Full, SimpleQueue and related classes.
"""
import importlib.util as _util
import sys as _sys
import sysconfig as _sysconfig
from pathlib import Path as _Path

_path = (_Path(_sys._MEIPASS) / 'queue.py' if getattr(_sys, 'frozen', False)
         else _Path(_sysconfig.get_path('stdlib')) / 'queue.py')
_spec = _util.spec_from_file_location('_viberush_stdlib_queue', _path)
_module = _util.module_from_spec(_spec)
_sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)
for _name in ('Queue','PriorityQueue','LifoQueue','SimpleQueue','Empty','Full','ShutDown'):
    if hasattr(_module,_name): globals()[_name] = getattr(_module,_name)
