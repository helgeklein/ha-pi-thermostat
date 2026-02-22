"""Conftest for unit tests.

Provides a direct-import helper so pure-Python modules (like pi_controller)
can be loaded without triggering the broken package __init__.py import chain
from old modules that haven't been rewritten yet.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_COMPONENTS_DIR = Path(__file__).resolve().parents[2] / "custom_components" / "pi_thermostat"


#
# import_module_direct
#
def import_module_direct(module_name: str) -> object:
    """Import a module directly from its file path, bypassing package __init__.py.

    This avoids the cascading import errors from old/unrewritten modules.
    """

    file_path = _COMPONENTS_DIR / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod
