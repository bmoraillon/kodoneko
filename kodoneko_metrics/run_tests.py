"""Runner minimal qui exécute les tests sans pytest installé."""
import sys
import inspect
import tempfile
import traceback
import types
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

# Mock minimal de pytest
pytest_mod = types.ModuleType("pytest")

class _Raises:
    def __init__(self, exc):
        self.exc = exc
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            raise AssertionError(f"Expected {self.exc} but no exception")
        return issubclass(exc_type, self.exc)
pytest_mod.raises = _Raises

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


class _MockTmpPath:
    def __init__(self):
        self._dir = tempfile.mkdtemp()
    def __truediv__(self, other):
        return Path(self._dir) / other
    def __str__(self):
        return self._dir


def run_test_module(module):
    passed, failed, skipped, failures = 0, 0, 0, []

    # Support module-level pytestmark = pytest.mark.skipif(...)
    pmark = getattr(module, "pytestmark", None)
    if pmark is not None:
        # _skipif returns a decorator ; we need to check if it set __skip__
        # via a fake target. Simpler : we re-execute the logic.
        # pytest.mark.skipif(cond, reason=...) was applied to nothing here,
        # but in pytest convention it skips the whole module.
        # Our mock _skipif() returns a decorator only ; we need a different path.
        # Convention : if pytestmark is callable and accepts a class, applying
        # it to a dummy reveals whether it skips.
        class _Probe: pass
        try:
            result = pmark(_Probe)
            if hasattr(result, "__skip__"):
                print(f"  ⏭ {module.__name__} (module skipped: {result.__skip__})")
                return 0, 0, 1, []
        except Exception:
            pass

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
            if "tmp_path" in sig.parameters:
                kwargs["tmp_path"] = _MockTmpPath()
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
    return passed, failed, skipped, failures


def main():
    print("=" * 60)
    print("test_analyzer")
    print("=" * 60)
    import test_analyzer as t1
    p1, f1, s1, fl1 = run_test_module(t1)

    print()
    print("=" * 60)
    print("test_cosmic")
    print("=" * 60)
    import test_cosmic as t2
    p2, f2, s2, fl2 = run_test_module(t2)

    print()
    print("=" * 60)
    print("test_cosmic_js")
    print("=" * 60)
    import test_cosmic_js as t3
    p3, f3, s3, fl3 = run_test_module(t3)

    print()
    print("=" * 60)
    print("test_cosmic_java")
    print("=" * 60)
    import test_cosmic_java as t4
    p4, f4, s4, fl4 = run_test_module(t4)

    print()
    print("=" * 60)
    print("test_analysis_report")
    print("=" * 60)
    import test_analysis_report as t5
    p5, f5, s5, fl5 = run_test_module(t5)

    p = p1 + p2 + p3 + p4 + p5
    f = f1 + f2 + f3 + f4 + f5
    s = s1 + s2 + s3 + s4 + s5
    fl = fl1 + fl2 + fl3 + fl4 + fl5

    print()
    print("=" * 60)
    print(f"RÉSULTAT : {p} passed, {f} failed, {s} skipped")
    print("=" * 60)

    if f > 0:
        print()
        for cls, meth, tb in fl:
            print()
            print(f"--- {cls}.{meth} ---")
            print(tb)

    return 0 if f == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
