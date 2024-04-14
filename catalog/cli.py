import os
import click
from catalog import Library
from catalog.process import transcribe
from contextualize.tokenize import call_tiktoken


@click.group()
def cli():
    pass


@click.command("transcribe")
@click.argument("query", nargs=-1)
@click.option(
    "--library",
    default="~/.config/catalog/library.json",
    help="Path to library file (default: ~/.config/catalog/library.json).",
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
    "--force",
    is_flag=True,
    help="Do not prompt for confirmation before transcribing media which already has transcripts.",
)
def transcribe_command(
    query,
    library,
    diarize,
    speaker_count,
    model,
    prompt,
    device_index,
    force,
):
    """Transcribe media objects."""
    library_path = os.path.expanduser(library)
    library = Library(library_path)

    media_objects = []
    for item in query:
        if os.path.isfile(item):
            try:
                media_object = library.import_media_object(item, auto=True)
                media_objects.append(media_object)
            except ValueError as e:
                click.echo(f"Error importing file {item}: {str(e)}")
        else:
            media_objects.extend(
                library.fetch(
                    ids=[item],
                )
            )
    click.echo(f"Imported/queried media objects: {len(media_objects)}")

    transcribe_queue = [obj for obj in media_objects if media_object.can_transcribe()]
    click.echo(f"Media objects to transcribe: {len(transcribe_queue)}")

    for media_object in transcribe_queue:
        if not media_object.can_transcribe():
            click.echo(f"Skipping {media_object.id[:5]} as it is not transcribable.")
            continue

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


cli.add_command(transcribe_command)
