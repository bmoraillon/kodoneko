#!/usr/bin/env python3
"""Runner de tests autonome pour kodoneko_temporal."""
import sys, inspect, traceback
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import setup_paths  # noqa
setup_paths.setup(verbose=False)
sys.path.insert(0, str(Path(__file__).parent / "tests"))

def run_test_module(module):
    p = f = s = 0; fails = []
    for cn, cls in inspect.getmembers(module, inspect.isclass):
        if not cn.startswith("Test"): continue
        inst = cls()
        for mn, meth in inspect.getmembers(inst, inspect.ismethod):
            if not mn.startswith("test_"): continue
            try:
                meth(); p += 1
            except Exception as e:
                f += 1; fails.append((f"{cn}.{mn}", e, traceback.format_exc()))
    return p, f, s, fails

def main():
    import test_temporal as t1
    import test_cosmic_delta as t2
    import test_windowing as t3
    total_p = total_f = total_s = 0
    all_fails = []
    for name, mod in [("test_temporal", t1), ("test_cosmic_delta", t2),
                      ("test_windowing", t3)]:
        print("="*60); print(name); print("="*60)
        p, f, s, fails = run_test_module(mod)
        total_p += p; total_f += f; total_s += s; all_fails += fails
    print()
    for name, err, tb in all_fails:
        print(f"✗ {name}: {type(err).__name__}: {err}"); print(tb)
    print("="*60)
    print(f"RÉSULTAT : {total_p} passed, {total_f} failed, {total_s} skipped")
    print("="*60)
    return 1 if total_f else 0

if __name__ == "__main__":
    sys.exit(main())
