"""Motion presets: declarative keyframe recipes that animate an overlay.

Public interface: :mod:`ive.motion.library` (the shareable JSON
catalogue) and :func:`ive.motion.runtime.make_motion` (recipe -> the
per-frame evaluator the engine calls). A preset is DATA, never code -
same rule as every other catalogue - so it shares, installs and rides
inside content packs like the rest.
"""

from ive.motion.library import (list_presets, preset_by_id, recipe_for,
                                sections, reload)
from ive.motion.runtime import attach_motion, make_motion

__all__ = ["list_presets", "preset_by_id", "recipe_for", "sections",
           "reload", "attach_motion", "make_motion"]
