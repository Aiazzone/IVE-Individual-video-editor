"""Can the project service lose the user's work? It could, five ways.

Every check here is a way a document on disk (or the open project in memory)
used to be destroyed or forked without the user asking for it:

* ``create()`` with a name that already exists silently replaced that
  project with an empty one - now it picks a numbered variant;
* ``rename()`` onto another project's name destroyed that project - now it
  refuses; and a rename whose save fails no longer leaves the model and the
  disk disagreeing about the name;
* ``close()`` discarded unsaved work when the final save failed - now it
  keeps the project open;
* ``open()`` blew up (out of any error signal) on valid JSON with a broken
  structure - now bad entries are skipped and a broken document is refused
  with the previous project left untouched;
* opening a file renamed in a file manager kept the OLD name stored inside,
  so every save went to a different file than the one opened - now the file
  name on disk wins.

All of it runs against temporary folders; nothing touches user_data.

    python tests/test_project_service_safety.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ive" / "src"))

results: list[tuple[bool, str]] = []


def check(condition: bool, message: str) -> None:
    results.append((bool(condition), message))
    print(f"  {'OK  ' if condition else 'FAIL'}  {message}")


def main() -> int:
    from PySide6.QtCore import QCoreApplication

    from ive.core.services.project_service import ProjectService

    QCoreApplication.instance() or QCoreApplication(sys.argv)

    with tempfile.TemporaryDirectory(prefix="ive-projsafety-") as tmp:
        folder = Path(tmp)
        errors: list[str] = []

        service = ProjectService()
        service.error.connect(errors.append)

        print("\n--- create() never overwrites ---")
        check(service.create("Vacanze", str(folder)), "a project is created")
        original = folder / "Vacanze.iveproj"
        marker = json.loads(original.read_text(encoding="utf-8"))["id"]
        check(service.create("Vacanze", str(folder)),
              "creating the same name again succeeds...")
        check(service.name == "Vacanze 2",
              f"...as a numbered variant ({service.name!r})")
        survived = json.loads(original.read_text(encoding="utf-8"))["id"]
        check(survived == marker, "and the existing document is untouched")

        print("\n--- rename() refuses a taken name, keeps state on failure ---")
        check(not service.rename("Vacanze"),
              "renaming onto another project is refused")
        check(any(e.startswith("name_taken") for e in errors),
              "with a name_taken error")
        check(service.name == "Vacanze 2"
              and (folder / "Vacanze 2.iveproj").is_file(),
              "and nothing moved")
        check(service.rename("Ferie"), "a rename to a free name works")
        check((folder / "Ferie.iveproj").is_file()
              and not (folder / "Vacanze 2.iveproj").exists(),
              "the file followed and the old one is gone")

        print("\n--- close() does not discard work when the save fails ---")
        blocker = folder / "blocked"
        blocker.write_text("a file, not a folder", encoding="utf-8")
        service._project.folder = str(blocker / "sub")   # save must fail here
        service._mark_dirty()
        check(not service.close(), "close() reports the failure")
        check(service.isOpen, "and the project is still open, work intact")
        service._project.folder = str(folder)            # make it savable again
        check(service.close(), "close() succeeds once saving can")

        print("\n--- open() survives broken documents ---")
        mangled = folder / "Mangled.iveproj"
        mangled.write_text(json.dumps({
            "name": "Mangled",
            "media": [
                {"path": "a.mp4", "duration": "abc", "width": None},
                {"no_path_at_all": True},
                "not even a dict",
            ],
            "timeline": [{"start": 1.0}],   # no media_id
            "extras": ["wrong shape"],
        }), encoding="utf-8")
        check(service.open(str(mangled)),
              "valid JSON with broken entries still opens")
        check(service.mediaCount == 1 and service.timelineCount == 0,
              f"bad entries are skipped, good ones kept "
              f"({service.mediaCount} media, {service.timelineCount} clips)")
        check(service.media[0]["duration"] == 0.0,
              "a wrong-typed field degrades to its default")

        before = len(errors)
        garbage = folder / "Garbage.iveproj"
        garbage.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        check(not service.open(str(garbage)),
              "a document that is not a project is refused")
        check(len(errors) > before, "with an error signal, not an exception")
        check(service.isOpen and service.name == "Mangled",
              "and the previously open project is untouched")

        print("\n--- a file renamed on disk keeps its disk name ---")
        renamed = folder / "RenamedByHand.iveproj"
        renamed.write_text((folder / "Ferie.iveproj").read_text(encoding="utf-8"),
                           encoding="utf-8")
        check(service.open(str(renamed)), "the renamed copy opens")
        check(service.name == "RenamedByHand",
              f"the name on disk wins ({service.name!r})")
        check(service.save() and service._project.file_path == renamed,
              "and saving writes back to the file that was opened")

        service.close()

    failed = [m for ok, m in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
