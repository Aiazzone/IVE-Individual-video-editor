"""Text and titles: rasterization of on-video text, and subtitle files.

Public interface: :func:`ive.text.raster.attach_text_sprites`,
:func:`ive.text.raster.render_text`, :func:`ive.text.raster.text_aspect`,
plus SRT/VTT reading and writing in :mod:`ive.text.subtitle_files`.
"""

from ive.text.raster import attach_text_sprites, render_text, text_aspect
from ive.text.subtitle_files import format_srt, format_vtt, parse_subtitles

__all__ = ["attach_text_sprites", "render_text", "text_aspect",
           "format_srt", "format_vtt", "parse_subtitles"]
