"""Text and titles: rasterization of on-video text.

Public interface: :func:`ive.text.raster.attach_text_sprites`,
:func:`ive.text.raster.render_text`, :func:`ive.text.raster.text_aspect`.
"""

from ive.text.raster import attach_text_sprites, render_text, text_aspect

__all__ = ["attach_text_sprites", "render_text", "text_aspect"]
