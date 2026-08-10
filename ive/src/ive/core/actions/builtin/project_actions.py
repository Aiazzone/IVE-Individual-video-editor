"""Actions for creating a project and filling its media pool."""

from __future__ import annotations

import logging

from ive.core.actions.registry import Param, action

log = logging.getLogger(__name__)


@action(
    id="project.new",
    title_key="project.new",
    desc_key="Create a project: a name and a folder to keep it in.",
    category="project",
    params={
        "name": Param(str, required=True, doc="Project name; no path separators."),
        "folder": Param(str, required=False,
                        doc="Where to store it. Defaults to user_data/projects."),
    },
    shortcut="Ctrl+N",
)
def new_project(ctx, name: str, folder: str = ""):
    if not ctx.require("project").create(name, folder):
        raise RuntimeError("Could not create the project")


@action(
    id="project.open",
    title_key="project.open",
    desc_key="Open an existing .iveproj file.",
    category="project",
    params={"path": Param(str, required=True)},
)
def open_project(ctx, path: str):
    if not ctx.require("project").open(path):
        raise RuntimeError("Could not open the project")


@action(
    id="project.save",
    title_key="project.save",
    desc_key="Write the project to disk.",
    category="project",
    shortcut="Ctrl+S",
)
def save_project(ctx):
    ctx.require("project").save()


@action(
    id="project.close",
    title_key="project.close",
    desc_key="Close the project, saving it first if needed.",
    category="project",
)
def close_project(ctx):
    ctx.require("project").close()


@action(
    id="project.rename",
    title_key="project.rename",
    desc_key="Rename the project; the file on disk follows.",
    category="project",
    params={"name": Param(str, required=True)},
)
def rename_project(ctx, name: str):
    ctx.require("project").rename(name)


@action(
    id="project.import_media",
    title_key="project.import_media",
    desc_key="Add files or folders to the media pool. Folders are scanned "
             "recursively for supported formats.",
    category="project",
    params={"paths": Param(list, required=True, doc="File or folder paths.")},
)
def import_media(ctx, paths: list):
    ctx.require("project").import_paths(list(paths))


@action(
    id="project.remove_media",
    title_key="project.remove_media",
    desc_key="Remove one item from the media pool. The file itself is not touched.",
    category="project",
    params={"media_id": Param(str, required=True)},
)
def remove_media(ctx, media_id: str):
    ctx.require("project").remove_media(media_id)


@action(
    id="project.preview_media",
    title_key="project.preview_media",
    desc_key="Load a pool item into the preview.",
    category="project",
    params={"media_id": Param(str, required=True)},
)
def preview_media(ctx, media_id: str):
    path = ctx.require("project").media_path(media_id)
    if not path:
        raise RuntimeError(f"Unknown media {media_id}")
    ctx.require("playback").open(path)
