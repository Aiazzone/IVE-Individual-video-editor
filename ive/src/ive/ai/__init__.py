"""AI tools: local models, explicit downloads, undoable results.

The contracts live in docs/AI_FEATURES.md. The principles that shape
this package: the app works with zero models installed (a missing model
is a state, not an error), weights are downloaded only on explicit
request with size and licence on show, every result enters the project
through a Command, and nothing of the user's leaves the machine.

Weights live in ``models/<task>/<model_id>/`` - the heavy sister folder,
untouched by app updates (see utils/paths.get_model_path).
"""

from ive.ai.downloader import ModelDownloadError, fetch_model
from ive.ai.model_registry import (
    MODELS,
    installed_bytes,
    is_installed,
    model_dir,
    model_entry,
    remove_model,
    translate_route,
)

__all__ = [
    "MODELS", "model_entry", "model_dir", "is_installed",
    "installed_bytes", "remove_model", "fetch_model", "ModelDownloadError",
    "translate_route",
]
