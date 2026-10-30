"""Build boundary-aware replacement patterns for private identity variants."""

from __future__ import annotations

import re

try:
    from tools import scan_public_repo as scanner
except ModuleNotFoundError:  # direct tools/export_public.py entry point
    import scan_public_repo as scanner

ARABIC = re.compile("[\u0600-\u06ff]")
ARABIC_LETTERS = "\u0621-\u064a\u0671-\u06d3"


def replacement_pattern(names: list[str], arabic: str, latin: str,
                        *, loose: bool = False) -> tuple[re.Pattern[str], dict[str, str]]:
    """Return a variant matcher and replacements keyed by its named groups.

    loose drops word boundaries to match the scanner's substring rule (identifiers such as
    a CamelCase class name, Arabic words with attached prefixes); an Arabic variant without
    the article then takes the replacement's stem, so a prefixed form keeps its prefix.
    """
    variants = sorted({variant for name in names for variant in scanner._name_variants(name)},
                      key=lambda variant: (-len(variant), variant))
    patterns = []
    replacements = {}
    for index, variant in enumerate(variants):
        group = f"name{index}"
        if ARABIC.search(variant):
            body = f"{scanner.ARABIC_MARKS.pattern}*".join(map(re.escape, variant))
            expression = body if loose else f"(?<![{ARABIC_LETTERS}]){body}(?![{ARABIC_LETTERS}])"
        elif variant.isascii():
            body = (r"[ \t\-_.]?".join(map(re.escape, variant))
                    if variant.isalnum() else re.escape(variant))
            expression = body if loose else rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])"
        else:
            expression = re.escape(variant)
        patterns.append(f"(?P<{group}>{expression})")
        if not ARABIC.search(variant):
            replacements[group] = latin
        elif loose and not variant.startswith("ال") and arabic.startswith("ال"):
            replacements[group] = arabic[2:]
        else:
            replacements[group] = arabic
    return re.compile("|".join(patterns), re.I), replacements
