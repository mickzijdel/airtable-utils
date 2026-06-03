import importlib.util
import sys
from pathlib import Path

BIN_DIR = Path(__file__).parent.parent / "bin"


def load_bin_script(name: str):
    """Load a bin/ script as a Python module (works despite hyphenated filenames)."""
    path = BIN_DIR / name
    module_name = name.replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
