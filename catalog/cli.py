import os
import sys
import click
import pyperclip
import tempfile
from datetime import datetime
from rich.console import Console
from rich.table import Table
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
    "--properties",
    "list_properties",
    is_flag=True,
    help="List queryable properties for the target object.",
)
@click.option(
    "--action",
    "-a",
    type=click.Choice(["edit", "play"]),
    help="Perform an action on the queried object: edit text in nvim (as tempfile) or play media in mpv.",
)
def query_command(
    target, subtarget, library, output, output_file, list_properties, action
):
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
        click.echo(
            f"Queryable properties for {media_object.id[:5]} ({media_object.__class__.__name__}):"
        )
        click.echo("\n".join(subtargets))
        return

    if subtarget:
        if subtarget in media_object.metadata:
            query_result = media_object.metadata.get(subtarget)
        else:
            query_result = getattr(media_object, subtarget, None)

            # replace transcript nodes with node count
            if subtarget == "transcripts":
                for transcript in query_result:
                    transcript["nodes"] = len(transcript["nodes"])

            if query_result is None:
                click.echo(f"Invalid subtarget: {subtarget}")
                return
    else:
        query_result = library.query(media_object)

    if action:
        output = None  # do not output to console
        if action == "edit":
            if isinstance(query_result, str):
                with tempfile.NamedTemporaryFile(mode="w", delete=False) as temp_file:
                    temp_file.write(query_result)
                    temp_file_path = temp_file.name
                os.system(f"nvim {temp_file_path} -R")
                os.unlink(temp_file_path)
            else:
                click.echo("The 'edit' option can only be used with string values.")
        elif action == "play":
            from catalog.media import Audio, Video

            if isinstance(media_object, (Audio, Video)):
                file_path = media_object.file_path
                if file_path:
                    os.system(f"mpv {file_path}")
                else:
                    click.echo(f"No file path found for {media_object.id[:5]}.")
            else:
                click.echo(
                    "The 'play' option can only be used with Audio or Video objects."
                )

    if output:
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
    """Transcribe compatible media objects."""
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


@click.command("add")
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
    type=click.Choice(["Audio", "Voice", "Video", "Image", "Screenshot", "Chat"]),
    help="Specify the MediaObject class for the imported file(s).",
)
@click.option(
    "--no-copy",
    is_flag=True,
    help="Do not copy imported files to the data directory when importing.",
)
def add_command(path, library, datastore, media_class, no_copy):
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
        media_object.set_text()
        click.echo(f"Stored processed text for {media_object.id[:5]}")
    except ValueError as e:
        click.echo(f"Error storing processed text: {str(e)}")

    try:
        library.save_library()
        click.echo(f"Changes saved to {library_path}.")
    except Exception as e:
        click.echo(f"Error saving library: {str(e)}")


@click.command("ls")
@click.option(
    "--library",
    default="~/.config/catalog/library.json",
    help="Path to library file (default: ~/.config/catalog/library.json).",
)
@click.option(
    "--sort",
    type=click.Choice(
        [
            "date",
            "date-asc",
            "transcripts",
            "transcripts-asc",
            "tokens",
            "tokens-asc",
        ],
        case_sensitive=False,
    ),
    default="date",
    help="Sort media objects by the specified criteria.",
)
@click.option("--page", is_flag=True, help="Display results in a pager.")
def ls_command(library, sort, page):
    """List media objects in a formatted table."""
    library_path = os.path.expanduser(library)
    library = Library(library_path)

    media_objects = library.media_objects

    def get_date(obj, key):
        date = getattr(obj, "metadata", {}).get(key)
        if date:
            return datetime.fromisoformat(date)
        return datetime.min

    sort_keys = {
        "date": lambda obj: get_date(obj, "date_created")
        or get_date(obj, "date_stored"),
        "date-asc": lambda obj: get_date(obj, "date_created")
        or get_date(obj, "date_stored"),
        "transcripts": lambda obj: -len(getattr(obj, "transcripts", [])),
        "transcripts-asc": lambda obj: len(getattr(obj, "transcripts", [])),
        "tokens": lambda obj: -getattr(obj, "metadata", {}).get("token_count", 0),
        "tokens-asc": lambda obj: getattr(obj, "metadata", {}).get("token_count", 0),
    }

    media_objects.sort(key=sort_keys[sort])

    table = Table(show_lines=True)
    table.add_column("ID", no_wrap=True)
    table.add_column("Name")
    table.add_column("Class")
    table.add_column("People")
    table.add_column("Segments", justify="right")
    table.add_column("Transcripts", justify="right")
    table.add_column("Date Created", justify="right")
    table.add_column("Date Stored", justify="right")

    for obj in media_objects:
        created = obj.metadata.get("date_created", "")
        stored = obj.metadata.get("date_stored", "")
        if obj.__class__.__name__ == "Chat":
            segments_count = len(getattr(obj, "messages", []))
        elif obj.__class__.__name__ == "Voice":
            # will set/fetch from library in future
            segments_count = round(
                sum(map(len, (t["nodes"] for t in obj.transcripts or [])))
                / (len(obj.transcripts) or 1)
            )

        transcripts_count = len(getattr(obj, "transcripts", []))
        people = (
            [name for name in obj.participants]
            if "participants" in obj.__dict__
            else []
        )
        people_str = ", ".join(people)

        if created:
            created = datetime.fromisoformat(created).strftime("%Y-%m-%d %H:%M:%S")
        if stored:
            stored = datetime.fromisoformat(stored).strftime("%Y-%m-%d %H:%M:%S")

        table.add_row(
            obj.id[:6],
            obj.metadata.get("name", "")
            if obj.metadata.get("name")
            else obj.metadata.get("source_filename", ""),
            obj.__class__.__name__,
            str(people_str),
            str(segments_count),
            str(transcripts_count),
            created,
            stored,
        )

    console = Console()
    if page:
        with console.pager():
            console.print(table)
    else:
        console.print(table)


@click.command(
    "rm",
    help="Remove media objects or specified entries by full or partial ID. "
    "Format: 'media_id[:type_id:entry_id]' (e.g. 'rm 65317 b3ab4', 'rm b3ab4:transcripts:6e2')",
)
@click.argument("targets", nargs=-1)
@click.option(
    "--library",
    default="~/.config/catalog/library.json",
    help="Path to library file (default: ~/.config/catalog/library.json).",
)
@click.option(
    "--delete-file",
    "-D",
    is_flag=True,
    help="Delete the associated file(s) from the datastore.",
)
def rm_command(targets, library, delete_file):
    library_path = os.path.expanduser(library)
    library = Library(library_path)

    try:
        for target in targets:
            parts = target.split(":")
            media_id = parts[0]
            if len(parts) == 1:
                # delete entire media object
                media_object = library.fetch([media_id])[0]
                message = f"Delete the entire media object '{media_object.id}'?"
                if delete_file:
                    message += (
                        " This will also delete the associated file from the datastore."
                    )
                if click.confirm(message, abort=True):
                    library.remove_media_object(media_object, delete_file=delete_file)
                    click.echo(f"Removed media object '{media_object.id}'")
            elif len(parts) == 2:
                # delete all entries of a specific type
                raise ValueError("not yet implemented")
            elif len(parts) == 3:
                # delete specific entry
                type_id, entry_id = parts[1], parts[2]
                if type_id in ["transcripts", "processed_text"]:
                    media_object, entry = library.fetch_entry(
                        media_id, type_id, entry_id
                    )
                    full_entry_id = entry["id"]
                    if click.confirm(
                        f"Delete {type_id} entry {full_entry_id} from '{media_object.id}'?",
                        abort=True,
                    ):
                        media_object.remove_entry(type_id, entry_id)
                        click.echo(
                            f"Removed {type_id} entry {full_entry_id} from '{media_object.id}'"
                        )

        library.save_library()
        click.echo(f"Changes saved to {library_path}.")

    except ValueError as e:
        click.echo(str(e))
    except Exception as e:
        click.echo(f"Error saving library: {str(e)}")


@click.command("md")
@click.argument("targets", nargs=-1)
@click.option(
    "--library",
    default="~/.config/catalog/library.json",
    help="Path to library file (default: ~/.config/catalog/library.json).",
)
@click.option(
    "--output-dir",
    default=".",
    help="Destination path for the generated pointers (default: current directory).",
)
def markdown_pointers_command(targets, library, output_dir):
    """Create Markdown files composed of specified objects' metadata and `text`.

    Targets can be media object IDs or file paths (which will be imported or matched to existing objects).
    """
    library_path = os.path.expanduser(library)
    library = Library(library_path)

    if not targets:
        media_objects = library.media_objects
    else:
        media_objects = prepare_objects(library, targets)

    for media_object in media_objects:
        try:
            library.create_pointer(media_object, dest_path=output_dir)
            click.echo(
                f"Created pointer for {media_object.id[:5]} ({media_object.__class__.__name__})"
            )
        except Exception as e:
            click.echo(f"Error creating pointer for {media_object.id[:5]}: {str(e)}")


cli.add_command(query_command)
cli.add_command(transcribe_command)
cli.add_command(add_command)
cli.add_command(store_command)
cli.add_command(ls_command)
cli.add_command(rm_command)
cli.add_command(markdown_pointers_command)
