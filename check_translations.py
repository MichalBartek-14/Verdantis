"""
Verifies every i18n key exists in every configured language, for every
page. Run this after adding/editing any docs/_template/*.html copy or
any docs/_template/assets/i18n/<lang>/*.json file - a mismatch means a
future addition to one language (almost always English, added first)
never made it into the other(s), which is exactly the drift this
project's i18n system exists to catch instead of silently shipping.

Exit code is non-zero on any mismatch, so this is safe to wire into a
pre-commit hook or CI step later if that becomes worth the overhead.

Run:    python check_translations.py
"""
import json
import sys
from pathlib import Path

I18N_DIR = Path("docs/_template/assets/i18n")


def flatten(obj, prefix=""):
    """dot.path -> leaf value, treating lists/strings/numbers as leaves
    (a translated string list, like month names, is one unit - it's the
    JSON *keys*, not array indices, that must match across languages)."""
    keys = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else k
            keys |= flatten(v, path)
    else:
        keys.add(prefix)
    return keys


def load(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    if not I18N_DIR.exists():
        print(f"No i18n directory at {I18N_DIR} - nothing to check.")
        return 0

    langs = sorted(p.name for p in I18N_DIR.iterdir() if p.is_dir())
    if len(langs) < 2:
        print(f"Only {len(langs)} language(s) configured ({', '.join(langs)}) - nothing to compare.")
        return 0

    # Every *.json filename (page name, e.g. "common", "index") that
    # exists for ANY language - so a page added for one language but
    # forgotten for another is caught too, not just missing keys within
    # a page both languages already have.
    pages = sorted({p.stem for lang in langs for p in (I18N_DIR / lang).glob("*.json")})

    problems = []
    for page in pages:
        per_lang_keys = {}
        for lang in langs:
            path = I18N_DIR / lang / f"{page}.json"
            if not path.exists():
                problems.append(f"[{page}] missing entirely for language \"{lang}\" (expected {path})")
                continue
            per_lang_keys[lang] = flatten(load(path))

        if len(per_lang_keys) < 2:
            continue
        all_keys = set().union(*per_lang_keys.values())
        for lang, keys in per_lang_keys.items():
            for missing in sorted(all_keys - keys):
                problems.append(f"[{page}] key \"{missing}\" missing in \"{lang}\"")

    print(f"Checked {len(pages)} page(s) across {len(langs)} language(s): {', '.join(langs)}")
    if problems:
        print(f"\n{len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        return 1

    print("All translation keys present in every language.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
