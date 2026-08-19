"""Content packs: one ``.ivepack`` file carrying shareable content.

Public interface: :mod:`ive.packs.pack` — build, preview, install,
list and remove packs. Everything inside a pack is DATA (JSON recipes
plus media files), never code: installing one is safe by construction
(docs/CONTENT_PACKS.md).
"""

from ive.packs.pack import (build_pack, installed_packs, install_pack,
                            preview_pack, remove_pack)

__all__ = ["build_pack", "preview_pack", "install_pack", "installed_packs",
           "remove_pack"]
