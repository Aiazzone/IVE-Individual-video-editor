"""Export social platforms and custom aspect ladder: data coherence.

The social tab now shows one icon per platform and reveals that platform's
presets on tap; the custom tab gained an aspect-ratio picker whose resolution
ladder is declared in QML. Both are data-driven, so what can rot is the DATA:
a preset pointing at a platform that has no icon, a platform with no presets
behind it, or a ladder entry whose numbers do not match its aspect. This
checks all of it without opening a window.

    python tests/test_export_platforms.py
"""

from __future__ import annotations

import re
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ive" / "src"))

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    print(f"  {'OK  ' if condition else 'FAIL'} {message}")
    if not condition:
        failures.append(message)


def main() -> int:
    from ive.export.presets import PLATFORMS, SOCIAL_PRESETS, preset_by_id

    platform_ids = {p["id"] for p in PLATFORMS}

    # ── presets ↔ platforms ───────────────────────────────────────────
    orphans = [p.id for p in SOCIAL_PRESETS if p.platform not in platform_ids]
    check(not orphans, f"every social preset belongs to a platform {orphans}")

    empty = [pid for pid in platform_ids
             if not any(p.platform == pid for p in SOCIAL_PRESETS)]
    check(not empty, f"every platform icon reveals at least one preset {empty}")

    first = {}
    for preset in SOCIAL_PRESETS:
        first.setdefault(preset.platform, preset.id)
    check(first.get("youtube") == "youtube_1080p",
          "youtube's first preset is the default the UI starts on")

    check(preset_by_id("instagram_stories") is not None,
          "the new instagram_stories preset resolves by id")

    maps = [p.to_map() for p in SOCIAL_PRESETS]
    check(all("platform" in m and "resolution" in m for m in maps),
          "to_map carries platform and resolution to QML")

    # ── every declared icon exists in Icons.qml ───────────────────────
    icons_qml = (ROOT / "ive" / "qml" / "components" / "Icons.qml").read_text(
        encoding="utf-8")
    missing = [p["icon"] for p in PLATFORMS
               if f"property string {p['icon']}:" not in icons_qml]
    check(not missing, f"every platform icon is drawn in Icons.qml {missing}")

    # ── the aspect ladder in QML is arithmetically honest ─────────────
    export_qml = (ROOT / "ive" / "qml" / "shell" / "ExportContent.qml").read_text(
        encoding="utf-8")
    ladders = re.findall(
        r'"(\d+x\d+)":\s*\[(.*?)\]', export_qml, flags=re.DOTALL)
    check(len(ladders) == 5, f"five aspect ladders declared ({len(ladders)})")

    for aspect, body in ladders:
        aw, ah = (int(n) for n in aspect.split("x"))
        want = Fraction(aw, ah)
        pairs = re.findall(r'value:\s*"(\d+)x(\d+)"', body)
        check(len(pairs) == 3, f"{aspect}: three tiers ({len(pairs)})")
        for w, h in pairs:
            w, h = int(w), int(h)
            check(w % 2 == 0 and h % 2 == 0,
                  f"{aspect}: {w}x{h} has even dimensions (yuv420p)")
            got = Fraction(w, h)
            # "21:9" is a marketing label: the real ultrawide standard is
            # 64:27 (2560x1080, 5120x2160), which is 2.37 to the label's
            # 2.33. The ladder ships the resolutions players actually use,
            # so the check tolerates the label's rounding.
            tolerance = 0.05 if aspect == "21x9" else 0.02
            check(abs(float(got) - float(want)) < tolerance,
                  f"{aspect}: {w}x{h} really is {aspect.replace('x', ':')}")

    # ── the translation hint exists for every aspect, in 4 locales ────
    for locale in ("en", "it", "es", "pt"):
        text = (ROOT / "ive" / "src" / "ive" / "i18n" / "locales"
                / f"{locale}.json").read_text(encoding="utf-8")
        absent = [a for a, _ in ladders if f'"export.aspect.{a}"' not in text]
        check(not absent, f"{locale}.json translates every aspect {absent}")

    print(f"\n{'PASS' if not failures else 'FAIL'} "
          f"({len(failures)} problem(s))")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
