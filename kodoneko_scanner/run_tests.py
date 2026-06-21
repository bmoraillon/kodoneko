"""Runner minimal qui exécute les tests sans pytest installé."""
import sys
import inspect
import os
import tempfile
import traceback
import types
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
# Dépendance : kodoneko_metrics est dans le répertoire frère
sys.path.insert(0, str(ROOT.parent / "kodoneko_metrics" / "src"))

# Mock minimal de pytest
pytest_mod = types.ModuleType("pytest")

class _Raises:
    def __init__(self, exc, match=None):
        self.exc = exc
        self.match = match
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            raise AssertionError(f"Expected {self.exc} but no exception")
        if not issubclass(exc_type, self.exc):
            return False
        if self.match and self.match not in str(exc_val):
            raise AssertionError(
                f"Exception message {str(exc_val)!r} doesn't contain {self.match!r}"
            )
        return True

def _raises(exc, match=None):
    return _Raises(exc, match=match)
pytest_mod.raises = _raises

def _skipif(condition, reason=""):
    def deco(cls_or_fn):
        if condition:
            cls_or_fn.__skip__ = reason
        return cls_or_fn
    return deco

class _Mark:
    skipif = staticmethod(_skipif)
pytest_mod.mark = _Mark()
pytest_mod.fixture = lambda f=None, **kw: (f if f else (lambda x: x))

class _Skipped(Exception):
    pass

def _skip(reason=""):
    raise _Skipped(reason)
pytest_mod.skip = _skip

sys.modules["pytest"] = pytest_mod


# Mini-monkeypatch pour les tests qui en ont besoin
class _MonkeyPatch:
    def __init__(self):
        self._env_saved = {}
        self._env_to_delete = []
        self._cwd_saved = None

    def setenv(self, key, value):
        if key not in self._env_saved:
            self._env_saved[key] = os.environ.get(key, _MISSING)
        os.environ[key] = value

    def delenv(self, key, raising=True):
        if key not in self._env_saved:
            self._env_saved[key] = os.environ.get(key, _MISSING)
        if key in os.environ:
            del os.environ[key]

    def chdir(self, path):
        if self._cwd_saved is None:
            self._cwd_saved = os.getcwd()
        os.chdir(path)

    def undo(self):
        for k, v in self._env_saved.items():
            if v is _MISSING:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        if self._cwd_saved is not None:
            os.chdir(self._cwd_saved)


_MISSING = object()


def _make_tmp_path():
    """Crée un répertoire temporaire et retourne un vrai Path."""
    return Path(tempfile.mkdtemp())


def run_test_module(module):
    passed, failed, skipped, failures = 0, 0, 0, []
    for cls_name, cls in inspect.getmembers(module, inspect.isclass):
        if not cls_name.startswith("Test"):
            continue
        if hasattr(cls, "__skip__"):
            print(f"  ⏭ {cls_name} (skipped: {cls.__skip__})")
            skipped += 1
            continue
        instance = cls()
        # Appeler setup_method si elle existe
        if hasattr(instance, "setup_method"):
            try:
                instance.setup_method()
            except _Skipped:
                continue
        for method_name, method in inspect.getmembers(instance, inspect.ismethod):
            if not method_name.startswith("test_"):
                continue
            sig = inspect.signature(method)
            kwargs = {}
            monkey = None
            if "tmp_path" in sig.parameters:
                kwargs["tmp_path"] = _make_tmp_path()
            if "monkeypatch" in sig.parameters:
                monkey = _MonkeyPatch()
                kwargs["monkeypatch"] = monkey
            try:
                method(**kwargs)
                passed += 1
                print(f"  ✓ {cls_name}.{method_name}")
            except _Skipped as s:
                skipped += 1
                print(f"  ⏭ {cls_name}.{method_name} (skip: {s})")
            except Exception as e:
                failed += 1
                failures.append((cls_name, method_name, traceback.format_exc()))
                print(f"  ✗ {cls_name}.{method_name} : {e}")
            finally:
                if monkey is not None:
                    monkey.undo()
    return passed, failed, skipped, failures


def main():
    total_p, total_f, total_s = 0, 0, 0
    all_failures = []

    for module_name in ("test_scanner", "test_config"):
        print("=" * 60)
        print(module_name)
        print("=" * 60)
        mod = __import__(module_name)
        p, f, s, fl = run_test_module(mod)
        total_p += p
        total_f += f
        total_s += s
        all_failures.extend(fl)
        print()

    print("=" * 60)
    print(f"RÉSULTAT : {total_p} passed, {total_f} failed, {total_s} skipped")
    print("=" * 60)

    if total_f > 0:
        print()
        for cls, meth, tb in all_failures:
            print()
            print(f"--- {cls}.{meth} ---")
            print(tb)

    return 0 if total_f == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
