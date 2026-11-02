"""Online content: everything the app can fetch, asked about ONCE.

Two kinds of download exist - the official content packs (music; files
on GitHub Releases, ive/packs/official.py) and the AI models
(ive/ai/model_registry.py). This service puts them behind one question
and one button, and owns the rules:

* at startup, when something is missing, the user is ASKED - nothing
  is fetched in silence;
* "Download" (whatever was ticked) answers the question for good;
* "Later" asks again at the next start, unless the "don't ask again"
  switch was on;
* Settings keeps a button that downloads whatever is still missing, and
  turns itself off once everything is there.

The models offered are the ones the features use by default - the
configured speech model, subject segmentation, VitTrack. Translation
pairs are per language (70-90 MB each) and stay on demand, fetched from
the translation card when a pair is actually needed.

The downloads themselves are the existing services' (PackService's
worker, SubtitleService's model fetcher); this one only coordinates.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Property, QObject, Signal, Slot

log = logging.getLogger(__name__)

__all__ = ["OnlineContentService", "CORE_MODELS"]

#: Models offered with the packs, besides the configured speech model.
CORE_MODELS = ("u2netp", "vittrack")


class OnlineContentService(QObject):
    """The startup question and the Settings button, over packs+models."""

    changed = Signal()

    def __init__(self, settings, packs, models,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._packs = packs
        self._models = models
        #: "Later" without the switch: quiet for THIS session only.
        self._dismissed = False
        for signal in (packs.officialChanged, models.stateChanged,
                       models.downloadChanged):
            signal.connect(self.changed)
        settings.changed.connect(self._on_setting)

    def _on_setting(self, key: str, _value) -> None:
        if key.startswith("online.") or key == "ai.subtitles_model":
            self.changed.emit()

    # ── what there is ─────────────────────────────────────────────────

    def _model_ids(self) -> list[str]:
        ids = []
        speech = str(self._settings.get("ai.subtitles_model") or "")
        if speech and self._models.state != "backend_missing":
            ids.append(speech)
        ids.extend(m for m in CORE_MODELS if m not in ids)
        return ids

    @Property("QVariantList", notify=changed)
    def items(self) -> list[dict]:
        """Every offered download: ``{id, kind ("pack"|"model"), name,
        sizeMb, license, installed}``, packs first."""
        out = []
        for pack in self._packs.official or []:
            out.append({"id": pack["id"], "kind": "pack",
                        "name": pack["name"], "sizeMb": pack["sizeMb"],
                        "license": pack["license"],
                        "installed": bool(pack["installed"])})
        models = {m["id"]: m for m in self._models.models or []}
        for model_id in self._model_ids():
            model = models.get(model_id)
            if model is None:
                continue
            out.append({"id": model_id, "kind": "model",
                        "name": model["name"],
                        "sizeMb": max(1, int(model["sizeMb"])),
                        "license": model["license"],
                        "installed": bool(model["installed"])})
        return out

    @Property("QVariantList", notify=changed)
    def missing(self) -> list[dict]:
        return [i for i in self.items if not i["installed"]]

    @Property(int, notify=changed)
    def missingMb(self) -> int:
        return sum(i["sizeMb"] for i in self.missing)

    @Property(bool, notify=changed)
    def complete(self) -> bool:
        """Everything offered is on disk: the Settings button goes off."""
        return not self.missing

    @Property(bool, notify=changed)
    def downloading(self) -> bool:
        return bool(self._packs.downloading or self._models.downloading)

    @Property(bool, notify=changed)
    def shouldOffer(self) -> bool:
        """Show the startup question now?"""
        if self._dismissed or self.complete or self.downloading:
            return False
        if self._settings.get("online.never_ask"):
            return False
        return not self._settings.get("online.offer_accepted")

    # ── what the user decides ─────────────────────────────────────────

    @Slot("QVariantList", bool, result=int)
    def download(self, ids, never_ask: bool = False) -> int:
        """Fetch the chosen items; the question is answered for good.

        Returns how many downloads were started.
        """
        ids = ids.toVariant() if hasattr(ids, "toVariant") else ids
        chosen = {str(i) for i in ids or []}
        missing = self.missing
        packs = [i["id"] for i in missing
                 if i["kind"] == "pack" and i["id"] in chosen]
        models = [i["id"] for i in missing
                  if i["kind"] == "model" and i["id"] in chosen]
        self._settings.set("online.offer_accepted", True)
        if never_ask:
            self._settings.set("online.never_ask", True)
        started = self._packs.download_many(packs) if packs else 0
        if models and self._models.download_many(models):
            started += len(models)
        log.info("Online content: %d pack(s), %d model(s) requested",
                 len(packs), len(models))
        self.changed.emit()
        return started

    @Slot(result=int)
    def download_all(self) -> int:
        """The Settings button: everything still missing."""
        return self.download([i["id"] for i in self.missing],
                             bool(self._settings.get("online.never_ask")))

    @Slot(bool)
    def dismiss(self, never_ask: bool = False) -> None:
        """"Later": quiet until the next start, or for good with the
        switch on."""
        self._dismissed = True
        if never_ask:
            self._settings.set("online.never_ask", True)
        self.changed.emit()
