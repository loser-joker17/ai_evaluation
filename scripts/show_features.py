"""Print the cached answer features the scoring caps depend on, one line per case.

Reads data/benchmark/results/state_cache/*.pkl (written by benchmark_fast.py). No model calls.

    python scripts\\show_features.py
    python scripts\\show_features.py visionias_gs3     # only ids containing this text
"""
import pickle
import sys
from pathlib import Path

CACHE = Path("data/benchmark/results/state_cache")


def get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def main():
    needle = sys.argv[1] if len(sys.argv) > 1 else ""
    print(f"{'case':<26}{'limit':>6}{'words':>6}{'status':>14}{'mech':>6}{'concl':>7}"
          f"{'spec/100':>9}{'unasked':>8}{'order':>7}  part shares")
    for p in sorted(CACHE.glob("*.pkl")):
        if needle not in p.stem:
            continue
        s = pickle.loads(p.read_bytes())
        f = s.get("answer_features") or {}
        print(f"{p.stem:<26}{str(s.get('word_limit')):>6}{str(s.get('word_count')):>6}"
              f"{str(s.get('word_limit_status')):>14}{str(get(f, 'mechanisms_explained')):>6}"
              f"{str(get(f, 'has_conclusion')):>7}{str(get(f, 'specifics_per_100_words')):>9}"
              f"{str(get(f, 'unasked_share')):>8}{str(get(f, 'parts_in_order')):>7}  "
              f"{[p['share'] for p in (get(f, 'part_word_share') or [])]}")


if __name__ == "__main__":
    main()