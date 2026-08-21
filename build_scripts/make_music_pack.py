"""Build the official music packs from Kevin MacLeod's catalogue.

Kevin MacLeod (incompetech.com) publishes his music under Creative
Commons Attribution 4.0: it may be redistributed and used commercially
as long as he is credited. That is exactly the licence a pack WE ship
needs (CLAUDE.md §4.9, docs/AUDIO.md §5). The site exposes its catalogue
as machine-readable data (pieces.json, genre.json - see
https://incompetech.com/llms.txt), so each pack is a CATEGORY RULE over
that catalogue: genres, moods ("feel"), a tempo range, no vocals - plus
one hand-picked list for "business", the first pack, kept stable.

    python build_scripts/make_music_pack.py                 # every category
    python build_scripts/make_music_pack.py lofi chill      # some
    python build_scripts/make_music_pack.py --dry-run       # list, no download
    python build_scripts/make_music_pack.py --out DIR       # destination

Downloads go to a cache under the output dir (re-runs are instant); each
category becomes ``ive-music-<category>.ivepack``. The MP3s are NOT
committed to the repository - packs are build artefacts, this script is
the source. Every track carries its source URL, licence and the
attribution line the app offers in credits.txt.
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

SITE = "https://incompetech.com/music/royalty-free/"
BASE = SITE + "mp3-royaltyfree/"
ARTIST = "Kevin MacLeod"
LICENSE = "CC-BY-4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
PER_PACK = 8
#: A bed longer than this is an album side, not a track for a cut.
MAX_SECONDS = 8 * 60
VOCAL_WORDS = ("vocal", "voice", "choir", "singer", "sing", "feat", "lyric",
               "chant", "rap")


def attribution(title: str) -> str:
    return (f'"{title}" Kevin MacLeod (incompetech.com) '
            f"Licensed under Creative Commons: By Attribution 4.0 License "
            f"{LICENSE_URL}")


#: Rules per category: which genres, which moods must / must not appear,
#: the tempo window. Tracks are instrumental by construction (VOCAL_WORDS
#: filter) and sorted newest first, so a rebuild picks the same set until
#: the catalogue grows.
CATEGORIES: dict[str, dict] = {
    "ambient": {
        "names": {"en": "Ambient", "it": "Ambient"},
        "genres": {"Contemporary", "Electronica"},
        "any": {"Calming", "Relaxed", "Calm"},
        "none": {"Dark", "Eerie", "Unnerving", "Intense", "Aggressive",
                 "Humorous", "Action", "Suspenseful"},
        "bpm": (0, 100),
        "blurb": {"en": "Slow, airy beds for calm scenes and voice-overs.",
                  "it": "Tappeti lenti e ariosi per scene calme e voce fuori campo."},
    },
    "upbeat": {
        "names": {"en": "Upbeat", "it": "Upbeat"},
        "genres": {"Pop", "Funk", "Electronica", "Disco", "Rock", "Ska"},
        "all": {"Bright"},
        "any": {"Bouncy", "Uplifting", "Driving"},
        "none": {"Dark", "Eerie", "Unnerving", "Somber", "Humorous",
                 "Intense", "Aggressive"},
        "bpm": (115, 200),
        "blurb": {"en": "Bright, driving tracks for energetic cuts.",
                  "it": "Brani luminosi e incalzanti per montaggi energici."},
    },
    "lofi": {
        "names": {"en": "Lo-fi", "it": "Lo-fi"},
        "genres": {"Jazz", "Urban", "Electronica", "Funk"},
        "any": {"Relaxed", "Grooving"},
        "none": {"Dark", "Intense", "Aggressive", "Eerie", "Humorous",
                 "Epic", "Action"},
        "bpm": (60, 96),
        "blurb": {"en": "Laid-back grooves at study-session tempo.",
                  "it": "Groove rilassati a tempo da sessione di studio."},
    },
    "chill": {
        "names": {"en": "Chill", "it": "Chill"},
        "genres": {"Jazz", "Electronica", "Contemporary", "Latin"},
        "any": {"Relaxed", "Calming"},
        "none": {"Dark", "Intense", "Aggressive", "Eerie", "Humorous",
                 "Epic", "Action", "Suspenseful"},
        "bpm": (85, 118),
        "blurb": {"en": "Easy-going, warm, never in a hurry.",
                  "it": "Disteso, caldo, mai di fretta."},
    },
    "pop": {
        "names": {"en": "Pop", "it": "Pop"},
        "genres": {"Pop", "Disco"},
        "any": {"Bright", "Bouncy", "Uplifting", "Grooving"},
        "none": {"Dark", "Eerie", "Unnerving", "Somber", "Aggressive",
                 "Intense"},
        "bpm": (95, 200),
        "blurb": {"en": "Catchy instrumental pop for social cuts.",
                  "it": "Pop strumentale orecchiabile per i video social."},
    },
    "corporate": {
        "names": {"en": "Corporate", "it": "Corporate"},
        "genres": {"Contemporary", "Electronica", "Modern"},
        "any": {"Uplifting", "Bright"},
        "none": {"Dark", "Eerie", "Unnerving", "Humorous", "Intense",
                 "Aggressive", "Somber", "Mysterious"},
        "bpm": (95, 132),
        "blurb": {"en": "Clean, confident beds for presentations and explainers.",
                  "it": "Tappeti puliti e sicuri per presentazioni e video esplicativi."},
    },
    # The first pack: hand-picked, kept as it shipped.
    "business": {
        "names": {"en": "Business", "it": "Business"},
        "titles": ["Inspired", "Wallpaper", "Carefree", "Deliberate Thought",
                   "Airport Lounge", "Easy Lemon", "Life of Riley",
                   "Floating Cities", "Digital Lemonade"],
        "blurb": {"en": "Instrumental, vocal-free tracks for technical and "
                        "corporate videos.",
                  "it": "Brani strumentali senza voce per video tecnici e "
                        "aziendali."},
    },
}


# ── catalogue ─────────────────────────────────────────────────────────

def fetch_json(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": "IVE/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def catalogue() -> list[dict]:
    genres = {str(g["id"]): g["genre"] for g in fetch_json(SITE + "genre.json")}
    pieces = fetch_json(SITE + "pieces.json")
    out = []
    for piece in pieces:
        title = str(piece.get("title") or "").strip()
        filename = str(piece.get("filename") or "").strip()
        if not title or not filename.lower().endswith(".mp3"):
            continue
        feel = {f.strip() for f in str(piece.get("feel") or "").split(",")
                if f.strip()}
        try:
            bpm = int(str(piece.get("bpm") or "0").strip() or 0)
        except ValueError:
            bpm = 0
        length = str(piece.get("length") or "00:00:00")
        try:
            h, m, s = (int(v) for v in length.split(":"))
            seconds = h * 3600 + m * 60 + s
        except ValueError:
            seconds = 0
        haystack = " ".join([title, str(piece.get("instruments") or ""),
                             str(piece.get("description") or "")]).lower()
        out.append({
            "title": title, "filename": filename,
            "genre": genres.get(str(piece.get("genre")), "?"),
            "feel": feel, "bpm": bpm, "seconds": seconds,
            "uploaded": str(piece.get("uploaded") or ""),
            "description": str(piece.get("description") or "").strip(),
            "vocals": any(w in haystack for w in VOCAL_WORDS),
        })
    return out


def select(category: str, pieces: list[dict], taken: set[str]) -> list[dict]:
    rule = CATEGORIES[category]
    if "titles" in rule:
        by_title = {p["title"]: p for p in pieces}
        return [by_title[t] for t in rule["titles"] if t in by_title]
    low, high = rule.get("bpm", (0, 999))
    found = []
    for piece in pieces:
        if piece["title"] in taken or piece["vocals"]:
            continue
        if piece["genre"] not in rule["genres"]:
            continue
        if not (low <= piece["bpm"] <= high):
            continue
        if not (60 <= piece["seconds"] <= MAX_SECONDS):
            continue
        if rule.get("all") and not rule["all"] <= piece["feel"]:
            continue
        if rule.get("any") and not (rule["any"] & piece["feel"]):
            continue
        if rule.get("none") and (rule["none"] & piece["feel"]):
            continue
        found.append(piece)
    found.sort(key=lambda p: (p["uploaded"], p["title"]), reverse=True)
    return found[:PER_PACK]


# ── building ──────────────────────────────────────────────────────────

def fetch_mp3(filename: str, cache: Path) -> Path | None:
    target = cache / filename
    if target.is_file() and target.stat().st_size > 100_000:
        return target
    url = BASE + urllib.parse.quote(filename)
    request = urllib.request.Request(url, headers={"User-Agent": "IVE/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read()
            kind = response.headers.get("Content-Type", "")
    except Exception as exc:   # noqa: BLE001 - a missing track is reported, not fatal
        print(f"  skip {filename}: {exc}")
        return None
    if "audio" not in kind and data[:3] not in (b"ID3", b"\xff\xfb", b"\xff\xf3"):
        print(f"  skip {filename}: not audio ({kind})")
        return None
    target.write_bytes(data)
    print(f"  fetched {filename} ({len(data) // 1024} KB)")
    return target


def slug(text: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def duration_of(path: Path, fallback: float) -> float:
    try:
        from ive.media.probe import probe

        return float(probe(path).duration or fallback)
    except Exception:
        return fallback


def build(category: str, chosen: list[dict], out_dir: Path) -> Path | None:
    rule = CATEGORIES[category]
    cache = out_dir / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    tracks, files = [], {}
    for piece in chosen:
        path = fetch_mp3(piece["filename"], cache)
        if path is None:
            continue
        track_id = f"km_{slug(piece['title'])}"
        arcname = f"{track_id}.mp3"
        files[arcname] = path
        tracks.append({
            "schema_version": 1,
            "id": track_id,
            "title": {"en": piece["title"]},
            "artist": ARTIST,
            "category": category,
            "tags": sorted(piece["feel"]) + [piece["genre"].lower()],
            "bpm": piece["bpm"],
            "vocals": False,
            "duration": round(duration_of(path, piece["seconds"]), 2),
            "description": piece["description"],
            "license": LICENSE,
            "license_url": LICENSE_URL,
            "source_url": BASE + urllib.parse.quote(piece["filename"]),
            "attribution_required": True,
            "attribution": attribution(piece["title"]),
            "file": f"files/{arcname}",
        })
    if not tracks:
        print(f"  {category}: nothing fetched")
        return None
    names = rule["names"]
    manifest = {
        "schema_version": 1,
        "id": f"ive-music-{category}",
        "name": f"{names['en']} music",
        "version": "1.0",
        "author": "IVE (music by Kevin MacLeod)",
        "description": {
            "en": f"{len(tracks)} tracks. {rule['blurb']['en']} Music by "
                  "Kevin MacLeod (incompetech.com), CC BY 4.0: credit him "
                  "in your video description - IVE offers the text at export.",
            "it": f"{len(tracks)} brani. {rule['blurb']['it']} Musica di "
                  "Kevin MacLeod (incompetech.com), CC BY 4.0: citalo nella "
                  "descrizione del video - IVE ti propone il testo all'export.",
        },
        "license": LICENSE,
        "attribution_required": True,
        "attribution_text": "Music by Kevin MacLeod (incompetech.com), "
                            "Licensed under Creative Commons: By Attribution "
                            "4.0",
        "tags": ["music", category, "instrumental"],
        "contents": {"music": [t["id"] for t in tracks]},
    }
    destination = out_dir / f"ive-music-{category}.ivepack"
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
    print(f"Pack written: {destination.name} ({len(tracks)} tracks, "
          f"{destination.stat().st_size // 1024 // 1024} MB)")
    return destination


def main() -> int:
    args = [a for a in sys.argv[1:]]
    dry = "--dry-run" in args
    out_dir = ROOT / "packs_out"
    if "--out" in args:
        out_dir = Path(args[args.index("--out") + 1])
        del args[args.index("--out"):args.index("--out") + 2]
    wanted = [a for a in args if not a.startswith("--")] or list(CATEGORIES)
    unknown = [w for w in wanted if w not in CATEGORIES]
    if unknown:
        print(f"Unknown categories: {unknown}. Known: {list(CATEGORIES)}")
        return 2

    print("Reading the incompetech catalogue...")
    pieces = catalogue()
    print(f"  {len(pieces)} pieces")
    taken: set[str] = set()
    # The hand-picked pack claims its titles first, so no rule steals them.
    for category in list(CATEGORIES):
        if "titles" in CATEGORIES[category]:
            taken.update(CATEGORIES[category]["titles"])
    failed = 0
    for category in wanted:
        chosen = select(category, pieces, taken)
        taken.update(p["title"] for p in chosen)
        print(f"\n[{category}] {len(chosen)} tracks")
        for p in chosen:
            print(f"  - {p['title']} ({p['genre']}, {p['bpm']} bpm, "
                  f"{p['seconds'] // 60}:{p['seconds'] % 60:02d}, "
                  f"{'/'.join(sorted(p['feel']))})")
        if not dry and build(category, chosen, out_dir) is None:
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
