import contextlib
import os
import sys
import tempfile
from datetime import datetime, timezone

import click
import pyperclip
import yaml
from contextualize.tokenize import call_tiktoken
from rich.console import Console
from rich.table import Table

from catalog import Group, Library
from catalog.embed import load_embeddings, reconcile_embeddings, vector_search
from catalog.process import process_transcript, transcribe
from catalog.utils import fetch_subtarget_entry, get_available_subtargets


def prepare_objects(library, query, type="media"):
    media_objects = []
    if type == "group":
        for group_id in query:
            group = library.fetch_group(group_id)
            if group:
                media_objects.extend(group.objects)
            else:
                click.echo(f"No group found with ID: {group_id}")
    else:
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


@click.command(
    "query",
    help="Query media objects by ID, property, entry type, entry index/ID, or (for speech_data) section/node index(es)."
    "Format: 'media_id[:property|entry_type[:entry_id|entry_index]]' (e.g. 'query 65317', 'query 65317:file_path', 'query 65317:transcripts', 'query 65317:transcripts:6e2', 'query 65317:speech_data', 'query 65317:speech_data:-1', 'query 65317:speech_data:-1.sections:0', 'query 65317:speech_data:-1.nodes:0-3'.",
)
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
    help="List non-empty queryable properties for the target object.",
)
@click.option(
    "--action",
    "-a",
    type=click.Choice(["nvim", "play"]),
    help="Perform an action on the queried object: edit text in nvim (as tempfile) or play media in mpv.",
)
@click.option(
    "--debug",
    is_flag=True,
    help="Print the section/node indices to be fetched instead of fetching them.",
)
@click.option(
    "--context",
    "-C",
    type=int,
    default=0,
    help="Show the specified number of surrounding nodes or sections.",
)
def query_command(
    target,
    subtarget,
    library,
    output,
    output_file,
    list_properties,
    action,
    debug,
    context,
):
    """Query media objects, groups, or tags."""
    library_path = os.path.expanduser(library)
    library = Library(library_path)

    if target.startswith("group:"):
        group_id = target.split(":", 1)[1]
        try:
            result = library.query_group(group_id, output="str")
        except ValueError as e:
            click.echo(str(e))
            return
    elif target.startswith("tag:"):
        tag_id = target.split(":", 1)[1]
        try:
            result = library.query_tag(tag_id, output="str")
        except ValueError as e:
            click.echo(str(e))
            return
    else:
        parts = target.split(":")
        media_id = parts[0]
        property = parts[1] if len(parts) > 1 else None
        entry_id = parts[2] if len(parts) > 2 else None

        subfield = None
        subfield_range = None

        if entry_id and "." in entry_id:
            entry_parts = entry_id.split(".")
            entry_id = entry_parts[0]
            subfield = entry_parts[1]
            if len(entry_parts) > 2:
                subfield_range = entry_parts[2]

        if subfield and subfield_range is None and ":" in target:
            subfield_range = target.split(":")[-1]

        media_objects = library.fetch([media_id])

        if not media_objects:
            click.echo(f"No media object found with ID: {media_id}")
            return

        media_object = media_objects[0]

        if list_properties:
            subtargets = get_available_subtargets(media_object)
            click.echo(
                f"Available properties for {media_object.id[:5]} ({media_object.__class__.__name__}):"
            )
            click.echo("\n".join(subtargets))
            return

        if property:
            if entry_id:
                if subfield in ["nodes", "sections"]:
                    entry = fetch_subtarget_entry(media_object, property, entry_id)
                    if not entry:
                        click.echo(f"No entry found for {entry_id}")
                        return

                    if debug:
                        click.echo(
                            f"Debug: Querying {subfield} with range {subfield_range}"
                        )
                        if subfield_range:
                            if "-" in subfield_range:
                                start, end = map(int, subfield_range.split("-"))
                                indices = range(start, end + 1)
                            else:
                                indices = [int(subfield_range)]
                        else:
                            indices = range(len(entry[subfield]))

                        click.echo(f"Indices to be fetched: {list(indices)}")
                        return

                    result = format_subfield(entry, subfield, subfield_range, context)
                else:
                    # Handle entry queries (media_id:entry_type:entry_id)
                    try:
                        entry = fetch_subtarget_entry(media_object, property, entry_id)
                        result = format_entry(entry, property, library)
                    except ValueError as e:
                        click.echo(str(e))
                        return
            else:
                # Property queries (including transcripts/speech_data)
                entries = getattr(media_object, property, None)
                if entries is None:
                    result = media_object.metadata.get(property)
                    if result is None:
                        click.echo(
                            f"Property or entry type '{property}' not found in media object."
                        )
                        return
                elif property in ["transcripts", "speech_data"]:
                    result = format_entries(entries, property, library)
                else:
                    result = entries
        else:
            result = library.query(media_object, output="str")

    if action:
        output = None  # do not output to console
        if action == "nvim":
            if isinstance(result, str):
                with tempfile.NamedTemporaryFile(mode="w", delete=False) as temp_file:
                    temp_file.write(result)
                    temp_file_path = temp_file.name
                os.system(f"nvim {temp_file_path} -c 'setfiletype markdown'")
                os.unlink(temp_file_path)
            else:
                click.echo("The 'nvim' option can only be used with string values.")
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
            click.echo(result)
        elif output == "clipboard":
            pyperclip.copy(str(result))
            token_count = call_tiktoken(str(result))["count"]
            click.echo(f"Copied {token_count} tokens to clipboard.")
        elif output == "file":
            if not output_file:
                click.echo("Output file path is required when --output is 'file'.")
                return
            with open(output_file, "w") as file:
                file.write(str(result))
            token_count = call_tiktoken(str(result))["count"]
            click.echo(f"Wrote {token_count} tokens to {output_file}.")


def format_entries(entries, entry_type, library):
    output = []
    for entry in entries:
        output.append(format_entry(entry, entry_type, library))
        output.append("\n")
    return "\n".join(output).strip()


def format_entry(entry, entry_type, library):
    def calculate_depth(nodes, index):
        depth = 0
        current_index = index
        while current_index is not None:
            current_node = next(
                (node for node in nodes if node["index"] == current_index), None
            )
            if current_node:
                current_index = current_node.get("parent")
                depth += 1
            else:
                current_index = None
        return depth - 1

    def format_node_content(node, previous_end):
        def insert_pause(previous_end, current_start, output, pause_duration):
            if current_start - previous_end > pause_duration:
                output.append("")

        content = node["content"].strip()
        speaker = node.get("speaker")
        result = []
        if previous_end is not None:
            pause_duration = 5
            insert_pause(previous_end, node["start"], result, pause_duration)
        if speaker:
            result.append(f"{speaker}: {content}")
        else:
            result.append(content)
        return "\n".join(result), node["end"]

    output = []
    previous_end = None

    if entry_type == "transcripts":
        for node in entry["nodes"]:
            formatted_content, previous_end = format_node_content(node, previous_end)
            output.append(formatted_content)

    elif entry_type == "speech_data":
        output.append(f"id: {entry['id']}")
        output.append(f"date stored: {entry['date_stored']}")
        output.append(f"source transcript: {entry['source_transcript']}")
        output.append(f"process mode: {entry['process_mode']}")
        output.append("parameters:")
        for param_key, param_value in entry["processor_params"].items():
            output.append(f"  {param_key}: {param_value}")
        tags = [library.get_tag_name(tag["id"]) for tag in entry.get("tags", [])]
        output.append("tags: " + ", ".join(tags))
        output.append("\n------------\n")
        for section in entry["sections"]:
            output.append(f"\n## {section['label']}")
            for index in range(section["indeces"][0], section["indeces"][1] + 1):
                message = next(
                    node for node in entry["nodes"] if node["index"] == index
                )
                depth = calculate_depth(entry["nodes"], index)
                indent = "  " * depth
                text = message["text"].strip()
                output.append(f"{indent}- {text}")
        output.append("\n============\n")

    return "\n".join(output).strip()


def format_subfield(entry, subfield, subfield_range, context=0):
    def format_nodes(entry, subfield_range, context):
        nodes = entry["nodes"]
        selected_nodes = []

        if subfield_range:
            if "-" in subfield_range:
                start, end = map(int, subfield_range.split("-"))
                selected_nodes = nodes[start : end + 1]
            else:
                index = int(subfield_range)
                selected_nodes = [nodes[index]]
        else:
            selected_nodes = nodes

        if context:
            start_index = max(
                0, min(node["index"] for node in selected_nodes) - context
            )
            end_index = min(
                len(nodes) - 1, max(node["index"] for node in selected_nodes) + context
            )
            selected_nodes = nodes[start_index : end_index + 1]

        return "\n".join(node["text"] for node in selected_nodes)

    def format_sections(entry, subfield_range, context):
        sections = entry["sections"]
        selected_sections = []

        if subfield_range:
            if "-" in subfield_range:
                start, end = map(int, subfield_range.split("-"))
                selected_sections = sections[start : end + 1]
            else:
                index = int(subfield_range)
                selected_sections = [sections[index]]
        else:
            selected_sections = sections

        if context:
            start_index = max(
                0, min(section["index"] for section in selected_sections) - context
            )
            end_index = min(
                len(sections) - 1,
                max(section["index"] for section in selected_sections) + context,
            )
            selected_sections = sections[start_index : end_index + 1]

        result = ""
        for section in selected_sections:
            result += f"section {sections.index(section)}: \"{section['label']}\"\n"
            for idx in range(section["indeces"][0], section["indeces"][1] + 1):
                result += f"{entry['nodes'][idx]['text']}\n"
        return result

    if subfield == "nodes":
        return format_nodes(entry, subfield_range, context)
    elif subfield == "sections":
        return format_sections(entry, subfield_range, context)
    else:
        return "Unsupported subfield type"


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
@click.option("--batch-size", type=int, default=16)
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
@click.option(
    "--missing",
    "process_missing",
    is_flag=True,
    help="Transcribe all transcribable media which do not have transcripts yet.",
)
def transcribe_command(
    query,
    library,
    datastore,
    diarize,
    speaker_count,
    model,
    prompt,
    batch_size,
    device_index,
    no_copy,
    force,
    process_missing,
):
    """Transcribe compatible media objects."""
    library_path = os.path.expanduser(library)
    datastore_path = os.path.expanduser(datastore)
    library = Library(library_path, datastore_path)

    if process_missing:
        media_objects = [
            obj
            for obj in library.media_objects
            if hasattr(obj, "can_transcribe")
            and obj.can_transcribe()
            and not obj.transcripts
        ]
        if not media_objects:
            click.echo("No transcribable media objects found without transcripts.")
            return
    else:
        query_type = "group" if query and query[0].startswith("group:") else "media"
        if query_type == "group":
            query = [q.split(":", 1)[1] for q in query]
        media_objects = prepare_objects(library, query, type=query_type)

    click.echo(f"Media objects to transcribe: {len(media_objects)}")

    for media_object in media_objects:
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
            with tempfile.TemporaryFile(mode="w+") as f:
                with contextlib.redirect_stdout(f), contextlib.redirect_stderr(f):
                    transcribe(
                        media_object,
                        diarize=diarize,
                        speaker_count=speaker_count,
                        whisper_version=model,
                        initial_prompt=prompt,
                        batch_size=batch_size,
                        device_index=device_index,
                    )
        except ValueError as e:
            from catalog.utils import clear_memory

            click.echo(f"Error transcribing {media_object.id[:5]}: {str(e)}")
            clear_memory()
            continue

        click.echo("Transcription completed.")

        token_count = call_tiktoken(media_object.get_markdown_str())["count"]
        click.echo(f"Token count: {token_count}")

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
@click.option(
    "--recursive",
    "-r",
    is_flag=True,
    help="When importing a directory, traverse and import from all subdirectories.",
)
def add_command(path, library, datastore, media_class, no_copy, recursive):
    """Import media from a file/directory or URL."""
    library_path = os.path.expanduser(library)
    datastore_path = os.path.expanduser(datastore)
    library = Library(library_path, datastore_path)

    initial_media_objects = library.media_objects.copy()
    imported_objects = []

    def import_path(item):
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

    def iterate_directory(directory):
        for root, _, files in os.walk(directory):
            for file in files:
                import_path(os.path.join(root, file))

    for item in path:
        if os.path.isdir(item):
            if recursive:
                iterate_directory(item)
            else:
                for file in os.listdir(item):
                    import_path(os.path.join(item, file))
        else:
            import_path(item)

    if imported_objects:
        try:
            library.save_library()
            click.echo(f"Changes saved to {library_path}.")
        except Exception as e:
            click.echo(f"Error saving library: {str(e)}")


@click.command("ls")
@click.argument("obj_target", required=False)
@click.option(
    "--library",
    default="~/.config/catalog/library.json",
    help="Path to library file (default: ~/.config/catalog/library.json).",
)
@click.option("--tags", is_flag=True, help="List (only) tags.")
@click.option("--groups", is_flag=True, help="List (only) groups.")
@click.option("--page", is_flag=True, help="Display results in a pager.")
@click.option(
    "--sort",
    type=str,
    help="Sort by specified fields (created, modified, stored, class, segments, transcripts, processed). Add :asc for ascending order (e.g., stored:asc). Multiple sorts can be comma-separated (e.g., class:asc,stored).",
)
@click.option(
    "--show",
    type=click.Choice(["count", "list"]),
    default="count",
    help="Whether to populate cells for groups/tags/entries with a count (default), or with a list of IDs.",
)
def ls_command(obj_target, library, tags, groups, page, sort, show):
    """List media objects in the library. Provide a target (eg 6e24a:speech_data) to list designated entries for a specific object; use --tags or --groups to list all objects of that type."""
    library_path = os.path.expanduser(library)
    library = Library(library_path)

    console = Console()

    if tags:
        table = prepare_tags_table(library)
        if page:
            with console.pager():
                console.print(table)
        else:
            console.print(table)
        return

    if groups:
        table = prepare_groups_table(library)
        if page:
            with console.pager():
                console.print(table)
        else:
            console.print(table)
        return

    if obj_target:
        parts = obj_target.split(":")
        media_id = parts[0]
        entry_type = parts[1] if len(parts) > 1 else None

        if entry_type:
            table = prepare_entries_table(library, media_id, entry_type)
            if page:
                with console.pager():
                    console.print(table)
            else:
                console.print(table)
            return

    media_objects = library.media_objects

    def get_date(obj, key):
        date = getattr(obj, "metadata", {}).get(key)
        if date:
            date = datetime.fromisoformat(date)
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            return date
        return datetime.min.replace(tzinfo=timezone.utc)

    def sort_key_generator(obj, sort_field):
        if sort_field in ["created", "modified", "stored", "recorded"]:
            return get_date(obj, f"date_{sort_field}")
        elif sort_field == "transcripts":
            return len(getattr(obj, "transcripts", []))
        elif sort_field == "segments":
            if obj.__class__.__name__ == "Chat":
                return len(getattr(obj, "messages", []))
            elif obj.__class__.__name__ == "Voice":
                return round(
                    sum(map(len, (t["nodes"] for t in obj.transcripts or [])))
                    / (len(obj.transcripts) or 1)
                )
            return 0
        elif sort_field == "class":
            return obj.__class__.__name__
        elif sort_field == "processed":
            return len(getattr(obj, "speech_data", []))
        elif sort_field == "tags":
            return len(getattr(obj, "metadata", {}).get("tags", []))
        elif sort_field == "groups":
            return len([g for g in library.groups if obj in g.objects])
        return None

    if sort:
        sort_criteria = sort.split(",")
    else:
        sort_criteria = ["recorded:desc"]  # default sort

    for criterion in reversed(sort_criteria):
        sort_parts = criterion.split(":")
        sort_field = sort_parts[0]
        sort_order = sort_parts[1] if len(sort_parts) > 1 else "desc"
        reverse_order = sort_order == "desc"

        if sort_field not in [
            "created",
            "modified",
            "stored",
            "class",
            "segments",
            "transcripts",
            "processed",
            "recorded",
            "tags",
            "groups",
        ]:
            raise ValueError(f"Invalid sort field: {sort_field}")

        media_objects.sort(
            key=lambda obj, field=sort_field: sort_key_generator(obj, field),
            reverse=reverse_order,
        )

    table = Table(show_lines=True)
    table.add_column("ID", no_wrap=True)
    table.add_column("Name")
    table.add_column("Class")
    table.add_column("Segments", justify="right")
    table.add_column("Tags", justify="right")
    table.add_column("Groups", justify="right")
    table.add_column("Transcripts", justify="right")
    table.add_column("Processed", justify="right")
    table.add_column("Date Recorded", justify="right")
    table.add_column("Date Stored", justify="right")

    for obj in media_objects:
        recorded = obj.metadata.get("date_recorded", "")
        stored = obj.metadata.get("date_stored", "")
        if obj.__class__.__name__ == "Chat":
            segments_count = len(getattr(obj, "messages", []))
        elif obj.__class__.__name__ == "Voice":
            segments_count = round(
                sum(map(len, (t["nodes"] for t in obj.transcripts or [])))
                / (len(obj.transcripts) or 1)
            )
        else:
            segments_count = 0

        transcripts_count = (
            len(getattr(obj, "transcripts", [])) if hasattr(obj, "transcripts") else 0
        )
        processed_count = (
            len(getattr(obj, "speech_data", [])) if hasattr(obj, "speech_data") else 0
        )

        tags_count = len(obj.metadata.get("tags", []))
        groups_count = len([g for g in library.groups if obj in g.objects])

        if recorded:
            recorded = datetime.fromisoformat(recorded).strftime("%Y-%m-%d %H:%M:%S")
        if stored:
            stored = datetime.fromisoformat(stored).strftime("%Y-%m-%d %H:%M:%S")

        tags_list = ", ".join(
            [
                f"{library.get_tag_name(tag['id'], mode='name')} ({tag['id'][:5]})"
                for tag in obj.metadata.get("tags", [])
            ]
        )
        groups_list = ", ".join(
            [
                f"{group.name} ({group.id[:5]})"
                for group in library.groups
                if obj in group.objects
            ]
        )

        transcripts_list = (
            ", ".join([entry["id"][:5] for entry in obj.transcripts])
            if hasattr(obj, "transcripts")
            else ""
        )
        processed_list = (
            ", ".join([entry["id"][:5] for entry in obj.speech_data])
            if hasattr(obj, "speech_data")
            else ""
        )

        if show == "list":
            tags_column = tags_list
            groups_column = groups_list
            transcripts_column = transcripts_list
            processed_column = processed_list
        else:
            tags_column = str(tags_count)
            groups_column = str(groups_count)
            transcripts_column = str(transcripts_count)
            processed_column = str(processed_count)

        table.add_row(
            obj.id[:6],
            obj.metadata.get("name", "")
            if obj.metadata.get("name")
            else obj.metadata.get("source_filename", ""),
            obj.__class__.__name__,
            str(segments_count),
            tags_column,
            groups_column,
            transcripts_column,
            processed_column,
            recorded,
            stored,
        )

    if page:
        with console.pager():
            console.print(table)
    else:
        console.print(table)


def prepare_entries_table(library, media_id, entry_type):
    table = Table(show_lines=True)
    table.add_column("ID", no_wrap=True)
    table.add_column("Tags", min_width=10)

    media_object = next(
        (obj for obj in library.media_objects if obj.id.startswith(media_id)), None
    )
    if not media_object:
        raise ValueError(f"No media object found with ID: {media_id}")

    entries = getattr(media_object, entry_type, [])
    for entry in entries:
        entry_id = entry.get("id", "")[:6]
        tags = [library.get_tag_name(tag["id"]) for tag in entry.get("tags", [])]
        tags_str = ", ".join(tags)

        table.add_row(entry_id, tags_str)

    return table


def prepare_tags_table(library):
    table = Table(show_lines=True)
    table.add_column("ID", no_wrap=True)
    table.add_column("Name")
    table.add_column("Parent(s)")
    table.add_column("Objects", justify="right")
    table.add_column("Entries", justify="right")

    tag_counts = {tag["id"]: {"objects": 0, "entries": 0} for tag in library.tags}

    for obj in library.media_objects:
        # count object tags
        for tag in obj.metadata.get("tags", []):
            tag_counts[tag["id"]]["objects"] += 1

        # count entry tags
        for entry_type in ["transcripts", "speech_data"]:
            for entry in getattr(obj, entry_type, []):
                for tag in entry.get("tags", []):
                    tag_counts[tag["id"]]["entries"] += 1

    sorted_tags = sorted(library.tags, key=lambda tag: tag["name"].lower())

    for tag in sorted_tags:
        tag_name = tag["name"]
        parent_names = [
            library.get_tag_name(parent) for parent in tag.get("parents", [])
        ]
        parent_names_str = ", ".join(parent_names)

        table.add_row(
            tag["id"][:6],
            tag_name,
            parent_names_str,
            str(tag_counts[tag["id"]]["objects"]),
            str(tag_counts[tag["id"]]["entries"]),
        )

    return table


def prepare_groups_table(library):
    table = Table(show_lines=True)
    table.add_column("ID", no_wrap=True)
    table.add_column("Name")
    table.add_column("Objects", justify="right")
    table.add_column("Subgroups", justify="right")
    table.add_column("Tags")
    table.add_column("Date Created", justify="right")

    for group in library.groups:
        name = group.name if group.name else "[untitled]"
        tags = [library.get_tag_name(tag_id) for tag_id in group.tags]
        tags_str = ", ".join(tags)
        table.add_row(
            group.id[:6],
            name,
            str(len(group.objects)),
            str(len(group.groups)),
            tags_str,
            group.date_created,
        )
    return table


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
                raise ValueError("Specify an entry ID for subtarget deletion.")
            elif len(parts) == 3:
                type_id, entry_id = parts[1], parts[2]
                if type_id in ["transcripts", "speech_data", "processed_text"]:
                    media_object = library.fetch([media_id])[0]
                    entry = fetch_subtarget_entry(media_object, type_id, entry_id)
                    full_entry_id = entry["id"]
                    if click.confirm(
                        f"Delete {type_id} entry {full_entry_id} from '{media_object.id}'?",
                        abort=True,
                    ):
                        media_object.remove_entry(type_id, full_entry_id)
                        click.echo(
                            f"Removed {type_id} entry {full_entry_id} from '{media_object.id}'"
                        )
                else:
                    raise ValueError(f"Invalid entry type: {type_id}")

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
@click.option("--mode", type=click.Choice(["default", "full"]), default="default")
@click.option(
    "--flatten",
    is_flag=True,
    help="Flatten indentation as needed to handle excessive nesting.",
)
def markdown_pointers_command(targets, library, output_dir, mode, flatten):
    """Create Markdown files composed of specified objects' metadata + textual representation ('default'), or all objects, along with all associated tags and groups ('full')."""

    library_path = os.path.expanduser(library)
    library = Library(library_path)

    if mode == "full":
        library.sync_pointers(output_dir)
    else:
        if not targets:
            click.echo("Error: No targets provided.")
            return

        for target in targets:
            if target.startswith("group:"):
                group_id = target.split(":", 1)[1]
                try:
                    group = library.fetch_group(group_id)
                    if group:
                        library.create_pointer(
                            group,
                            dest_path=output_dir,
                            mode=mode,
                            flatten_excess=flatten,
                        )
                    else:
                        click.echo(f"No group found with ID: {group_id}")
                except ValueError as e:
                    click.echo(str(e))
            elif target.startswith("tag:"):
                tag_str = target.split(":", 1)[1]
                try:
                    tag_id = library.get_tag_id(tag_str)
                    library.create_pointer(
                        tag_id, dest_path=output_dir, mode=mode, flatten_excess=flatten
                    )
                except ValueError as e:
                    click.echo(str(e))
            else:
                media_objects = library.fetch([target])
                for media_object in media_objects:
                    try:
                        library.create_pointer(
                            media_object,
                            dest_path=output_dir,
                            mode=mode,
                            flatten_excess=flatten,
                        )
                        click.echo(
                            f"Created pointer for {media_object.id[:5]} ({media_object.__class__.__name__})"
                        )
                    except Exception as e:
                        click.echo(
                            f"Error creating pointer for {media_object.id[:5]}: {str(e)}"
                        )


@click.command("process")
@click.argument("targets", nargs=-1)
@click.option(
    "--library",
    default="~/.config/catalog/library.json",
    help="Path to library file (default: ~/.config/catalog/library.json).",
)
@click.option("--transcript", help="Transcript index or UUID to use for processing.")
@click.option(
    "--config",
    type=click.Path(exists=True),
    help="Path to a YAML configuration file containing processing parameters.",
)
@click.option(
    "--missing",
    "process_missing",
    is_flag=True,
    help="Process all transcribed media which has not yet been processed.",
)
def process_command(targets, library, transcript, config, process_missing):
    """Process a media object's data (only transcripts currently supported) using a specified configuration."""
    library_path = os.path.expanduser(library)
    library = Library(library_path)

    if process_missing:
        targets = [
            obj.id
            for obj in library.media_objects
            if hasattr(obj, "transcripts") and obj.transcripts and not obj.speech_data
        ]

    if not targets:
        click.echo("Error: At least one target must be provided.")
        return

    query_type = "group" if targets and targets[0].startswith("group:") else "media"
    if query_type == "group":
        targets = [t.split(":", 1)[1] for t in targets]
    media_objects = prepare_objects(library, targets, type=query_type)
    print(f"Objects to process: {len(media_objects)}")

    if not config:
        click.echo("Error: --config must be provided.")
        return

    try:
        with open(config, "r") as file:
            sim_params = yaml.safe_load(file)
    except Exception as e:
        click.echo(f"Error loading configuration file: {str(e)}")
        return

    for media_object in media_objects:
        try:
            process_transcript(media_object, transcript, sim_params)
            click.echo(f"Processed transcript for {media_object.id[:5]}")
        except Exception as e:
            click.echo(
                f"Error processing transcript for {media_object.id[:5]}: {str(e)}"
            )
            continue

    try:
        library.save_library()
        click.echo(f"Changes saved to {library_path}.")
    except Exception as e:
        click.echo(f"Error saving library: {str(e)}")


@click.command("export")
@click.argument("target")
@click.option(
    "--format",
    default="md",
    help="Output format: 'md' (Markdown), 'sexp' (S-expression).",
)
@click.option(
    "--library",
    default="~/.config/catalog/library.json",
    help="Path to library file (default: ~/.config/catalog/library.json).",
)
def export_command(target, format, library):
    """Export text data of a media object."""
    library_path = os.path.expanduser(library)
    library = Library(library_path)

    media_objects = prepare_objects(library, [target])

    if not media_objects:
        click.echo(f"No media object found with ID: {target}")
        return

    media_object = media_objects[0]

    try:
        data = media_object.export_text(format=format)
        click.echo(data)
    except ValueError as e:
        click.echo(f"Error: {str(e)}")


@click.command("tag")
@click.argument("target", required=False)
@click.argument("tag_str", required=False)
@click.option("--create", "-c", is_flag=True, help="Create a new tag.")
@click.option(
    "--library",
    default="~/.config/catalog/library.json",
    help="Path to library file (default: ~/.config/catalog/library.json).",
)
@click.option(
    "--remove",
    is_flag=True,
    help="Remove the specified tag instead of assigning it.",
)
def tag_command(target, tag_str, create, library, remove):
    """Assign, remove, or create tags for a media object or entry."""
    library_path = os.path.expanduser(library)
    library = Library(library_path)

    if create:
        if not target:
            click.echo("Error: Tag name is required to create a tag.")
            return
        tag_name = target
        parent_id = library.get_tag_id(tag_str) if tag_str else None
        library.create_tag(tag_name, parent_id, description="")
        library.save_library()
        click.echo(f"Tag '{tag_name}' created.")
    else:
        if not tag_str or not target:
            click.echo(
                "Error: Both tag name and target are required when not creating a new tag."
            )
            return
        try:
            if target.startswith("group:"):
                group_id = target.split(":", 1)[1]
                group = library.fetch_group(group_id)
                if not group:
                    click.echo(f"No group found with ID: {group_id}")
                    return
                if remove:
                    library.untag_group(group, tag_str)
                else:
                    library.tag_group(group, tag_str)
            else:
                parts = target.split(":")
                media_id = parts[0]
                media_object = library.fetch([media_id])[0]

                if len(parts) == 3:
                    entry_type, entry_id = parts[1], parts[2]
                    if entry_type not in ["transcripts", "speech_data"]:
                        click.echo(f"Error: Invalid entry type '{entry_type}'.")
                        return

                    if remove:
                        tag_id = library.get_tag_id(tag_str)
                        library.untag_entry(media_object, entry_type, entry_id, tag_id)
                    else:
                        library.tag_entry(
                            media_object, entry_type, entry_id, tag_str=tag_str
                        )
                else:
                    if remove:
                        tag_id = library.get_tag_id(tag_str)
                        library.untag_object(media_object, tag_id)
                    else:
                        library.tag_object(media_object, tag_str=tag_str)

            library.save_library()
            click.echo(f"Tag operation successful for {target}.")

        except ValueError as e:
            click.echo(f"Error: {str(e)}")
        except Exception as e:
            click.echo(f"Unexpected error: {str(e)}")


@click.command("manage")
@click.argument("target", type=str)
@click.argument(
    "action",
    type=click.Choice(["rename", "set-desc", "set-parent", "remove-parent", "rm"]),
)
@click.argument("param", required=False)
@click.option(
    "--library",
    default="~/.config/catalog/library.json",
    help="Path to library file (default: ~/.config/catalog/library.json).",
)
@click.option(
    "--parent",
    "-p",
    help="Parent tag or group name or ID to set or remove.",
)
def manage_command(target, action, param, library, parent):
    """Manage a tag, group, or media object. Usage: 'manage [tag|group]:[id|tag/group name] [action] [param]'."""
    library_path = os.path.expanduser(library)
    library = Library(library_path)

    if target.startswith("tag:"):
        tag_str = target.split(":", 1)[1]
        manage_tag(action, tag_str, param, library, parent)
    elif target.startswith("group:"):
        group_str = target.split(":", 1)[1]
        manage_group(action, group_str, param, library, parent)
    else:
        manage_object(action, target, param, library)


def manage_object(action, obj_id, param, library):
    try:
        media_object = library.fetch([obj_id])[0]

        if action == "rename":
            if not param:
                click.echo("Error: New name is required to rename an object.")
                return
            media_object.metadata["name"] = param
            library.save_library()
            click.echo(f"Object '{media_object.id}' renamed to '{param}'.")

        elif action == "set-desc":
            if not param:
                if click.confirm("No description provided. Clear?", default=True):
                    media_object.description = ""
            if os.path.isfile(param):
                with open(param, "r") as file:
                    media_object.description = file.read().strip()
            else:
                media_object.description = param.strip()
            library.save_library()
            click.echo(f"Description for object '{media_object.id}' updated.")

    except ValueError as e:
        click.echo(f"Error: {str(e)}")
    except Exception as e:
        click.echo(f"Unexpected error: {str(e)}")


def manage_tag(action, tag_str, param, library, parent):
    try:
        tag_id = library.get_tag_id(tag_str)
        tag = next(tag for tag in library.tags if tag["id"] == tag_id)
        tag_label = f"'{tag['name']}' ({tag_id[:6]})"

        if action == "rename":
            if not param:
                click.echo("Error: New name is required to rename a tag.")
                return
            library.rename_tag(tag_id, param)
            library.save_library()
            click.echo(f"Tag {tag_label} renamed to '{param}'.")
            return

        if action == "set-parent":
            parent_id = library.get_tag_id(parent or param)
            if not parent_id:
                click.echo("Error: Parent tag is required to set a parent tag.")
                return
            library.add_parent_tag(tag_id, parent_id)
            library.save_library()
            click.echo(f"Parent tag '{parent or param}' added to {tag_label}.")
            return

        if action == "remove-parent":
            parent_id = library.get_tag_id(parent or param)
            if not parent_id:
                click.echo("Error: Parent tag is required to remove a parent tag.")
                return
            library.remove_parent_tag(tag_id, parent_id)
            library.save_library()
            click.echo(f"Parent tag '{parent or param}' removed from {tag_label}.")
            return

        if action == "set-desc":
            if os.path.isfile(param):
                with open(param, "r") as file:
                    description = file.read().strip()
            else:
                description = param.strip()

            tag = next(tag for tag in library.tags if tag["id"] == tag_id)
            tag["description"] = description

            library.save_library()
            click.echo(f"Description for tag {tag_label} updated.")
            return

        if action == "rm":
            assignments_count = library.count_tag_assignments(tag_id)
            if not click.confirm(
                f"Tag {tag_label} is assigned to {assignments_count} items. Do you want to delete it?"
            ):
                return
            library.delete_tag(tag_id)
            library.save_library()
            click.echo("Tag deleted.")
            return

    except ValueError as e:
        click.echo(f"Error: {str(e)}")
    except Exception as e:
        click.echo(f"Unexpected error: {str(e)}")


def manage_group(action, group_str, param, library, parent):
    try:
        group = library.fetch_group(group_str)
        if not group:
            click.echo(f"No group found with ID: {group_str}")
            return

        group_name = group.name or group_str

        if action == "rename":
            if not param:
                click.echo("Error: New name is required to rename a group.")
                return
            group.name = param
            library.save_library()
            click.echo(f"Group '{group_name}' renamed to '{param}'.")
            return

        if action == "set-parent":
            parent_group = library.fetch_group(parent or param)
            if not parent_group:
                click.echo(
                    "Error: Valid parent group is required to set a parent group."
                )
                return
            if parent_group.id == group.id:
                click.echo("Error: A group cannot be its own parent.")
                return
            if group in parent_group.groups:
                click.echo(
                    "Error: This group is already a subgroup of the parent group."
                )
                return
            parent_group.add_groups([group])
            library.save_library()
            click.echo(
                f"Parent group '{parent_group.name or parent_group.id[:6]}' added to '{group_name}'."
            )
            return

        if action == "remove-parent":
            parent_group = library.fetch_group(parent or param)
            if not parent_group:
                click.echo(
                    "Error: Valid parent group is required to remove a parent group."
                )
                return
            if group.id not in [subgroup.id for subgroup in parent_group.groups]:
                click.echo("Error: This group is not a subgroup of the parent group.")
                return
            parent_group.groups = [
                subgroup for subgroup in parent_group.groups if subgroup.id != group.id
            ]
            library.save_library()
            click.echo(
                f"Parent group '{parent_group.name or parent_group.id[:6]}' removed from '{group_name}'."
            )
            return

        if action == "set-desc":
            if os.path.isfile(param):
                with open(param, "r") as file:
                    description = file.read().strip()
            else:
                description = param.strip()
            group.description = description
            library.save_library()
            click.echo(f"Description for group '{group_name}' updated.")
            return

        if action == "rm":
            if not click.confirm(
                f"Are you sure you want to delete the group '{group_name}'?"
            ):
                return
            library.delete_group(group.id)
            click.echo(f"Group '{group_name}' deleted.")
            return

    except ValueError as e:
        click.echo(f"Error: {str(e)}")
    except Exception as e:
        click.echo(f"Unexpected error: {str(e)}")


@click.command("search")
@click.argument("query", required=False)
@click.option(
    "--mode",
    type=click.Choice(["exact", "fuzzy", "embeddings"]),
    default="exact",
    help="Search mode: 'exact' (default), 'fuzzy', or 'embeddings'.",
)
@click.option(
    "--max-results",
    type=int,
    default=10,
    help="Maximum number of results to return (default: 10).",
)
@click.option(
    "--threshold",
    type=int,
    default=80,
    help="Minimum match score for fuzzy search (default: 80).",
)
@click.option(
    "--cs",
    "case_sensitive",
    is_flag=True,
    default=False,
    help="Search case-sensitive (default: False).",
)
@click.option(
    "--search-all",
    is_flag=True,
    default=False,
    help="Search through all entries (default: False).",
)
@click.option(
    "--sync",
    is_flag=True,
    default=False,
    help="Synchronize embeddings before search (default: False).",
)
@click.option(
    "--library",
    default="~/.config/catalog/library.json",
    help="Path to library file (default: ~/.config/catalog/library.json).",
)
@click.option(
    "-e",
    "--embeddings",
    "use_embeddings",
    is_flag=True,
    help="Use embeddings mode for vector search.",
)
def search_command(
    query,
    mode,
    max_results,
    threshold,
    case_sensitive,
    search_all,
    sync,
    library,
    use_embeddings,
):
    """Search media objects in the library."""
    library_path = os.path.expanduser(library)
    library = Library(library_path)

    if sync:
        click.echo("Updating embeddings...")
        reconcile_embeddings(library, device="gpu")
        click.echo("Embeddings updated.")
        if not query:
            return

    if use_embeddings or mode == "embeddings":
        embeddings, locators = load_embeddings()
        search_results = vector_search(
            query, embeddings, locators, top_k=max_results, device="gpu"
        )
        for i, result in enumerate(search_results, 1):
            click.echo(f"- {result[0]}")
    else:
        search_results = library.search(
            query=query,
            mode=mode,
            max_results=max_results,
            threshold=threshold,
            ignore_case=not case_sensitive,
            full_search=search_all,
        )
        for result, locator in search_results:
            click.echo(f"- {result} ({locator})")

    if not search_results:
        click.echo("No results found.")
        return


@click.command(
    "edit",
    help="Set the content of a node within an entry to a new value. Usage: catalog edit [locator] '[updated/corrected value]'.",
)
@click.argument("locator")
@click.argument("new_content")
def edit_command(locator, new_content):
    """Edit the content of a specific node within a media object entry."""
    from catalog.utils import update_node_content

    try:
        update_node_content(locator, new_content)
        click.echo("Node content updated.")
    except ValueError as e:
        click.echo(f"Error: {str(e)}")
    except Exception as e:
        click.echo(f"Unexpected error: {str(e)}")


@click.command("group")
@click.argument("ids", nargs=-1)
@click.argument("name", required=True)
@click.option(
    "--description",
    "-d",
    default="",
    help="Optional description (for use when creating a new group).",
)
@click.option(
    "--library", default="~/.config/catalog/library.json", help="Path to library file."
)
@click.option(
    "--nested-groups",
    "-g",
    default="",
    help="Comma-separated list of group IDs to include as subgroups (when creating a new group).",
)
def group_command(ids, name, description, library, nested_groups):
    """Create or update a group with specified media objects. Usage: 'group [ids] [name] [options]'."""
    library_path = os.path.expanduser(library)
    library = Library(library_path)

    try:
        group = library.fetch_group(name)
        click.echo(f"Group '{name}' exists with ID: {group.id}. Updating...")
    except ValueError:
        if not ids:
            if click.confirm(f"Group '{name}' does not exist. Create a new group?"):
                group = Group(name=name, description=description)
                library.groups.append(group)
                click.echo(f"Created new group '{name}'.")
            else:
                return
        else:
            group = Group(name=name, description=description)
            library.groups.append(group)
            click.echo(f"Created new group '{name}'.")

    if ids:
        print(f"Adding objects: {ids}")
        objects = library.fetch(ids)
        group.add_objects(objects)

    if nested_groups:
        print(f"Adding subgroups: {nested_groups}")
        subgroup_ids = nested_groups.split(",")
        subgroups = [library.fetch_group(group_id) for group_id in subgroup_ids]
        subgroups = [group for group in subgroups if group is not None]
        group.add_groups(subgroups)

    library.save_library()


cli.add_command(query_command)
cli.add_command(transcribe_command)
cli.add_command(add_command)
cli.add_command(ls_command)
cli.add_command(rm_command)
cli.add_command(markdown_pointers_command)
cli.add_command(process_command)
cli.add_command(export_command)
cli.add_command(tag_command)
cli.add_command(manage_command)
cli.add_command(search_command)
cli.add_command(edit_command)
cli.add_command(group_command)
