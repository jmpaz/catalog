import os
import shutil
import subprocess
from datetime import datetime
from core.transcribe import Transcriber, to_lrc
from rich.console import Console
from rich.progress import Progress, TextColumn, BarColumn, SpinnerColumn


def sync_files(source_dirs, dest_dir="data/imports", use_delete=True, logger=None):
    console = Console()

    for source_dir in source_dirs:
        synced_files = []
        deleted_files = []
        changes_made = False  # Flag to track if any changes were made

        try:
            source_dir = os.path.join(source_dir, "")
            base_name = os.path.basename(source_dir.rstrip("/"))
            dest_path = os.path.join(dest_dir, base_name)

            # Construct rsync command
            command = ["rsync", "-avz"]
            if use_delete:
                command.append("--delete")
            command.extend([source_dir, dest_path])

            with subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            ) as proc:
                if proc.stdout:
                    for line in proc.stdout:
                        clean_line = line.strip()
                        console.log(clean_line)

                        # Check if the line is a file operation and filter out rsync status messages
                        if clean_line and not any(
                            clean_line.startswith(prefix)
                            for prefix in [
                                "sending incremental file list",
                                "sent ",
                                "total size ",
                                "created directory",
                            ]
                        ):
                            changes_made = True  # A file operation is present
                            if clean_line.startswith("deleting "):
                                deleted_file = clean_line.replace("deleting ", "")
                                deleted_files.append(deleted_file)
                            elif (
                                clean_line != "./"
                                and "/" not in clean_line
                                and not clean_line.endswith(":")
                            ):
                                synced_files.append(clean_line)

                if proc.wait() != 0:
                    raise subprocess.CalledProcessError(proc.returncode, command)

            # Log the file operations after the synchronization is complete
            if logger:
                logger.log_file_process(synced_files, deleted_files, dest_path)

            if not changes_made:
                console.log(
                    f"\n{dest_path} is up to date; no changes were made.",
                )

        except subprocess.CalledProcessError as e:
            if logger:
                logger.error(f"rsync failed for {source_dir}. Error: {e}")
            else:
                console.log(f"[bold red]rsync failed for {source_dir}. Error: {e}")


def process_rsync_output(line, dest_path, logger):
    # Check if the line indicates a file sync or deletion
    if line.startswith("deleting "):
        deleted_file = line.replace("deleting ", "").strip()
        if logger:
            logger.info(f"Deleted file from {dest_path}: {deleted_file}")
    elif line and not line.startswith("sent ") and not line.startswith("total size "):
        synced_file = line.strip()
        if logger:
            logger.info(f"Synchronized file to {dest_path}: {synced_file}")


def format_duration(duration):
    total_seconds = int(duration.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    duration_parts = []
    if hours:
        duration_parts.append(f"{hours}h")
    if minutes or (hours and not seconds):
        duration_parts.append(f"{minutes}m")
    if seconds or not (hours or minutes):
        duration_parts.append(f"{seconds}s")

    return " ".join(duration_parts)


class AudioHandler:
    def __init__(self, args, logger, console):
        self.args = args
        self.logger = logger
        self.console = console
        self.transcriber = Transcriber(device_index=args.device_index)
        self.temp_dir = ".tmp" if args.format == "lrc" else args.output
        os.makedirs(self.temp_dir, exist_ok=True)

    def transcribe(self):
        print(f"Transcribe command received for {self.args.input_path}.\n")
        self.logger.start_session(self.args)

        if not os.path.exists(self.args.input_path):
            raise FileNotFoundError(
                f"Input path {self.args.input_path} does not exist."
            )
        elif os.path.isdir(self.args.input_path) and not os.listdir(
            self.args.input_path
        ):
            raise FileNotFoundError(f"Input directory {self.args.input_path} is empty.")

        if not os.path.exists(self.args.output):
            os.makedirs(self.args.output)

        if os.path.isdir(self.args.input_path):
            self.process_directory(self.args.input_path)
        else:
            self.process_audio_file(self.args.input_path)

        self.finalize_lrc()
        self.logger.end_session()

    def process_audio_file(self, file_path):
        start_time = datetime.now()
        if self.args.verbose:
            print(f"Transcribing {file_path}...")

        self.transcriber.call_whisperx(
            file_path,
            self.temp_dir,
            output_format="srt",
            speaker_count=self.args.speaker_count,
            initial_prompt=self.args.prompt,
        )

        if self.args.relocate_files == "true":
            shutil.move(file_path, self.args.output)

        end_time = datetime.now()
        self.logger.log_file_process(file_path, start_time, end_time)

        if self.args.verbose:
            print(
                f"Finished processing {file_path} in {format_duration(end_time - start_time)}\n"
            )

    def process_directory(self, directory_path):
        self.console.print(f"Processing directory: {directory_path}", style="bold")
        start_time = datetime.now()

        def is_supported(filename):
            supported_extensions = ["flac", "m4a", "mp3", "mp4", "ogg", "wav", "webm"]
            return os.path.isfile(os.path.join(directory_path, filename)) and any(
                filename.endswith(ext) for ext in supported_extensions
            )

        # Filter out non-audio files and directories
        file_list = sorted(filter(is_supported, os.listdir(directory_path)))
        total_files = len(file_list)

        with Progress(
            "[progress.description]{task.description}",
            BarColumn(bar_width=40),
            TextColumn("[bold]{task.fields[file_count]}", justify="right"),
            SpinnerColumn(spinner_name="dots", style="bold green"),
            console=self.console,
        ) as progress:
            task_id = progress.add_task(
                "", total=total_files, file_count=f"0/{total_files}"
            )
            for index, filename in enumerate(file_list, start=1):
                file_path = os.path.join(directory_path, filename)
                self.process_audio_file(file_path)
                progress.update(task_id, advance=1, file_count=f"{index}/{total_files}")

        end_time = datetime.now()
        duration = format_duration(end_time - start_time)
        self.console.print(
            f"Finished processing {total_files} files in {duration}.",
            style="green bold",
        )

    def finalize_lrc(self):
        if os.path.exists(self.temp_dir) and self.args.format == "lrc":
            to_lrc(self.temp_dir, self.args.output)
            shutil.rmtree(self.temp_dir)
