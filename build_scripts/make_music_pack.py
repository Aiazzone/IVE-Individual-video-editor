"""Build the official "Business" music pack from Kevin MacLeod's catalogue.

Kevin MacLeod (incompetech.com) publishes his music under Creative
Commons Attribution 4.0: it may be redistributed and used commercially
as long as he is credited. That is exactly the licence a pack WE ship
needs (CLAUDE.md §4.9, docs/AUDIO.md §5). The track list below is
instrumental, vocal-free, "corporate / technical video" material; every
entry carries its source URL and the attribution text the app offers in
credits.txt.

    python build_scripts/make_music_pack.py [destination_dir]

Downloads go to a cache next to the output (re-runs are instant); the
result is ``ive-music-business.ivepack``. The MP3s are NOT committed to
the repository - the pack is a build artefact, this script is the
source.
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ive" / "src"))

BASE = "https://incompetech.com/music/royalty-free/mp3-royaltyfree/"
ARTIST = "Kevin MacLeod"
LICENSE = "CC-BY-4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"


def attribution(title: str) -> str:
    return (f'"{title}" Kevin MacLeod (incompetech.com) '
            f"Licensed under Creative Commons: By Attribution 4.0 License "
            f"{LICENSE_URL}")


#: (file title as on incompetech, id, names, bpm, mood tags)
TRACKS = [
    ("Inspired", "km_inspired",
     {"en": "Inspired", "it": "Inspired"}, 120, ["uplifting", "corporate"]),
    ("Wallpaper", "km_wallpaper",
     {"en": "Wallpaper", "it": "Wallpaper"}, 110, ["light", "background"]),
    ("Carefree", "km_carefree",
     {"en": "Carefree", "it": "Carefree"}, 130, ["bright", "ukulele"]),
    ("Deliberate Thought", "km_deliberate_thought",
     {"en": "Deliberate Thought", "it": "Deliberate Thought"}, 100,
     ["calm", "piano", "technical"]),
    ("Cipher", "km_cipher",
     {"en": "Cipher", "it": "Cipher"}, 100, ["electronic", "technical"]),
    ("Airport Lounge", "km_airport_lounge",
     {"en": "Airport Lounge", "it": "Airport Lounge"}, 100,
     ["lounge", "smooth"]),
    ("Easy Lemon", "km_easy_lemon",
     {"en": "Easy Lemon", "it": "Easy Lemon"}, 95, ["piano", "calm"]),
    ("Life of Riley", "km_life_of_riley",
     {"en": "Life of Riley", "it": "Life of Riley"}, 120, ["upbeat", "bright"]),
    ("Floating Cities", "km_floating_cities",
     {"en": "Floating Cities", "it": "Floating Cities"}, 90,
     ["ambient", "calm"]),
    ("Digital Lemonade", "km_digital_lemonade",
     {"en": "Digital Lemonade", "it": "Digital Lemonade"}, 125,
     ["electronic", "upbeat"]),
]


def fetch(title: str, cache: Path) -> Path | None:
    target = cache / f"{title}.mp3"
    if target.is_file() and target.stat().st_size > 100_000:
        return target
    url = BASE + urllib.parse.quote(f"{title}.mp3")
    request = urllib.request.Request(url, headers={"User-Agent": "IVE/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
            kind = response.headers.get("Content-Type", "")
    except Exception as exc:   # noqa: BLE001 - a missing track is reported, not fatal
        print(f"  skip {title}: {exc}")
        return None
    if "audio" not in kind and not data[:3] in (b"ID3", b"\xff\xfb", b"\xff\xf3"):
        print(f"  skip {title}: not audio ({kind})")
        return None
    target.write_bytes(data)
    print(f"  fetched {title} ({len(data) // 1024} KB)")
    return target


def duration_of(path: Path) -> float:
    try:
        from ive.media.probe import probe

        return float(probe(path).duration or 0.0)
    except Exception:
        return 0.0


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "packs_out"
    cache = out_dir / "cache"
    cache.mkdir(parents=True, exist_ok=True)

    tracks = []
    files: dict[str, Path] = {}
    for title, track_id, names, bpm, tags in TRACKS:
        path = fetch(title, cache)
        if path is None:
            continue
        arcname = f"{track_id}.mp3"
        files[arcname] = path
        tracks.append({
            "schema_version": 1,
            "id": track_id,
            "title": names,
            "artist": ARTIST,
            "category": "business",
            "tags": tags,
            "bpm": bpm,
            "vocals": False,
            "duration": round(duration_of(path), 2),
            "license": LICENSE,
            "license_url": LICENSE_URL,
            "source_url": BASE + urllib.parse.quote(f"{title}.mp3"),
            "attribution_required": True,
            "attribution": attribution(names["en"]),
            "file": f"files/{arcname}",
        })
    if not tracks:
        print("No track could be fetched.")
        return 1

    manifest = {
        "schema_version": 1,
        "id": "ive-music-business",
        "name": "Business music",
        "version": "1.0",
        "author": "IVE (music by Kevin MacLeod)",
        "description": {
            "en": f"{len(tracks)} instrumental, vocal-free tracks for "
                  "technical and corporate videos. Music by Kevin MacLeod "
                  "(incompetech.com), CC BY 4.0: credit him in your video "
                  "description - IVE offers the text at export.",
            "it": f"{len(tracks)} brani strumentali senza voce per video "
                  "tecnici e aziendali. Musica di Kevin MacLeod "
                  "(incompetech.com), CC BY 4.0: citalo nella descrizione "
                  "del video - IVE ti propone il testo all'export.",
        },
        "license": LICENSE,
        "attribution_required": True,
        "attribution_text": "Music by Kevin MacLeod (incompetech.com), "
                            "Licensed under Creative Commons: By Attribution "
                            "4.0",
        "tags": ["music", "business", "corporate", "instrumental"],
        "contents": {"music": [t["id"] for t in tracks]},
    }
    destination = out_dir / "ive-music-business.ivepack"
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("pack.json", json.dumps(manifest, ensure_ascii=False,
                                                 indent=2))
        archive.writestr("music/tracks.json", json.dumps(tracks,
                                                         ensure_ascii=False,
                                                         indent=2))
        archive.writestr("LICENSE.txt", "\n".join(
            [manifest["attribution_text"], LICENSE_URL, ""]
            + [t["attribution"] for t in tracks]))
        for arcname, path in files.items():
            archive.write(path, f"music/files/{arcname}")
    print(f"Pack written: {destination} ({len(tracks)} tracks, "
          f"{destination.stat().st_size // 1024 // 1024} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
