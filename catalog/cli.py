import os
import sys
import click
import pyperclip
from catalog import Library
from catalog.process import transcribe
from contextualize.tokenize import call_tiktoken


def prepare_objects(library, query):
    media_objects = []
    for item in query:
        if os.path.isfile(item):
            try:
                media_object = library.import_media_object(item, auto=True)
                media_objects.append(media_object)
            except ValueError as e:
                click.echo(f"Error handling file {item}: {str(e)}")
        else:
            media_objects.extend(library.fetch(ids=[item]))
    return media_objects


@click.group()
def cli():
    pass


@click.command("query")
@click.argument("target")
@click.argument("subtarget", required=False)
@click.option(
    "--library",
    default="~/.config/catalog/library.json",
    help="Path to library file (default: ~/.config/catalog/library.json).",
)
@click.option(
    "--output",
    type=click.Choice(["console", "file", "clipboard"]),
    default="console",
    help="Output destination (default: console).",
)
@click.option(
    "--output-file",
    type=click.Path(writable=True),
    help="Output file path (required when --output is 'file').",
)
@click.option(
    "--list-properties",
    is_flag=True,
    help="List queryable properties for the target object.",
)
def query_command(target, subtarget, library, output, output_file, list_properties):
    """Query media objects."""
    library_path = os.path.expanduser(library)
    library = Library(library_path)

    media_objects = prepare_objects(library, [target])

    if not media_objects:
        click.echo(f"No media object found with ID: {target}")
        return

    media_object = media_objects[0]

    if list_properties:
        subtargets = get_subtargets(media_object)
        click.echo("Available subtargets:")
        click.echo("\n".join(subtargets))
        return

    if subtarget:
        if subtarget in media_object.metadata:
            query_result = media_object.metadata.get(subtarget)
        else:
            query_result = getattr(media_object, subtarget, None)
            if query_result is None:
                click.echo(f"Invalid subtarget: {subtarget}")
                return
    else:
        query_result = library.query(media_object)

    if output == "console":
        click.echo(query_result)
    elif output == "clipboard":
        pyperclip.copy(str(query_result))
        token_count = call_tiktoken(str(query_result))["count"]
        click.echo(f"Copied {token_count} tokens to clipboard.")
    elif output == "file":
        if not output_file:
            click.echo("Output file path is required when --output is 'file'.")
            return
        with open(output_file, "w") as file:
            file.write(str(query_result))
        token_count = call_tiktoken(str(query_result))["count"]
        click.echo(f"Wrote {token_count} tokens to {output_file}.")


def get_subtargets(media_object):
    from catalog.media import MediaObject

    if not isinstance(media_object, MediaObject):
        raise ValueError("Invalid media object")

    subtargets = []
    for attr in dir(media_object):
        if not attr.startswith("_") and not callable(getattr(media_object, attr)):
            subtargets.append(attr)
    for key in media_object.metadata:
        subtargets.append(key)
    return subtargets


@click.command("transcribe")
@click.argument("query", nargs=-1)
@click.option(
    "--library",
    default="~/.config/catalog/library.json",
    help="Path to library file (default: ~/.config/catalog/library.json).",
)
@click.option(
    "--datastore",
    default="~/.local/share/catalog/datastore",
    help="Path to data directory (for copying imported files, default: ~/.local/share/catalog/datastore).",
)
@click.option(
    "--model",
    default="large-v2",
    help="Whisper model to use, e.g., 'large-v2' (default), 'large-v3'.",
)
@click.option("--prompt", help="Initial prompt to use for transcription.")
@click.option("--diarize", is_flag=True, help="Enable diarization.")
@click.option("--speaker-count", type=int, help="Number of speakers for diarization.")
@click.option("--device-index", type=int, default=0)
@click.option(
    "--no-copy",
    is_flag=True,
    help="Do not copy imported files to the data directory when importing.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Do not prompt for confirmation before transcribing media which already has transcripts.",
)
def transcribe_command(
    query,
    library,
    datastore,
    diarize,
    speaker_count,
    model,
    prompt,
    device_index,
    no_copy,
    force,
):
    """Transcribe media objects."""
    library_path = os.path.expanduser(library)
    datastore_path = os.path.expanduser(datastore)
    library = Library(library_path, datastore_path)

    media_objects = prepare_objects(library, query)
    transcribe_queue = [obj for obj in media_objects if obj.can_transcribe()]
    click.echo(f"Media objects to transcribe: {len(transcribe_queue)}")

    for media_object in transcribe_queue:
        if not force and media_object.transcripts:
            num_transcripts = len(media_object.transcripts)
            if not click.confirm(
                f"{media_object.id[:5]} already has {num_transcripts} transcript(s). Transcribe anyway?"
            ):
                continue
        else:
            num_transcripts = len(media_object.transcripts)
            click.echo(
                f"{media_object.id[:5]} has {num_transcripts} existing transcript(s). Transcribing..."
            )

        click.echo(f"Starting transcription for {media_object.id[:5]}...")

        try:
            transcribe(
                media_object,
                diarize=diarize,
                speaker_count=speaker_count,
                whisper_version=model,
                initial_prompt=prompt,
                device_index=device_index,
            )
        except ValueError as e:
            click.echo(f"Error transcribing {media_object.id[:5]}: {str(e)}")
            continue

        click.echo(f"Transcription completed for {media_object.id[:5]}.")

        media_object.set_text()
        token_count = call_tiktoken(media_object.text)["count"]
        click.echo(f"Token count for {media_object.id[:5]}: {token_count}")

    try:
        library.save_library()
        click.echo(f"Changes saved to {library_path}.")
    except Exception as e:
        click.echo(f"Error saving library: {str(e)}")


@click.command("import")
@click.argument("path", nargs=-1)
@click.option(
    "--library",
    default="~/.config/catalog/library.json",
    help="Path to library file (default: ~/.config/catalog/library.json).",
)
@click.option(
    "--datastore",
    default="~/.local/share/catalog/datastore",
    help="Path to data directory (for copying imported files, default: ~/.local/share/catalog/datastore).",
)
@click.option(
    "--class",
    "media_class",
    type=click.Choice(["Audio", "Voice", "Video", "Image", "Screenshot"]),
    help="Specify the MediaObject class for the imported file(s).",
)
@click.option(
    "--no-copy",
    is_flag=True,
    help="Do not copy imported files to the data directory when importing.",
)
def import_command(path, library, datastore, media_class, no_copy):
    """Import media files or URLs."""
    library_path = os.path.expanduser(library)
    datastore_path = os.path.expanduser(datastore)
    library = Library(library_path, datastore_path)

    initial_media_objects = library.media_objects.copy()
    imported_objects = []

    for item in path:
        if os.path.isfile(item) or item.startswith(("http://", "https://")):
            try:
                media_object_class = (
                    getattr(sys.modules["catalog.media"], media_class)
                    if media_class
                    else None
                )
                media_object = library.import_media_object(
                    item,
                    media_object_class=media_object_class,
                    auto=not media_class,
                    make_copy=not no_copy,
                )
                if media_object not in initial_media_objects:
                    imported_objects.append(media_object)
                    click.echo(
                        f"Imported {media_object.id[:5]} ({media_object.__class__.__name__})"
                    )
                else:
                    click.echo(
                        f"Found existing object {media_object.id[:5]} ({media_object.__class__.__name__})"
                    )
            except ValueError as e:
                click.echo(f"Error importing {item}: {str(e)}")
        else:
            click.echo(f"Skipping {item} (not a file or URL)")

    if imported_objects:
        try:
            library.save_library()
            click.echo(f"Changes saved to {library_path}.")
        except Exception as e:
            click.echo(f"Error saving library: {str(e)}")


@click.command("store")
@click.argument("id")
@click.argument("text", type=click.File("r"))
@click.option(
    "--library",
    default="~/.config/catalog/library.json",
    help="Path to library file (default: ~/.config/catalog/library.json).",
)
@click.option("--source", help="Source of the processed text.")
@click.option("--label", help="Label for the processed text entry.")
def store_command(id, text, library, source, label):
    """Store processed text for a media object."""
    library_path = os.path.expanduser(library)
    library = Library(library_path)

    media_objects = prepare_objects(library, [id])

    if not media_objects:
        click.echo(f"No media object found with ID: {id}")
        return

    media_object = media_objects[0]
    processed_text = text.read().strip()

    try:
        media_object.store_processed_text(processed_text, source=source, label=label)
        click.echo(f"Stored processed text for {media_object.id[:5]}")
    except ValueError as e:
        click.echo(f"Error storing processed text: {str(e)}")

    try:
        library.save_library()
        click.echo(f"Changes saved to {library_path}.")
    except Exception as e:
        click.echo(f"Error saving library: {str(e)}")


cli.add_command(query_command)
cli.add_command(transcribe_command)
cli.add_command(import_command)
cli.add_command(store_command)
