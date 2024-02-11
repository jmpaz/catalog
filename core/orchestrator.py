import os
from datetime import datetime
import shutil
from core.transcribe import Transcriber, to_lrc
from utils.file_handling import format_duration
from utils.export import export_markdown, parse_file_details
from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn, SpinnerColumn


class Orchestrator:
    def __init__(
        self,
        audio_input_path,
        final_audio_output_dir,
        final_md_output_dir,
        transcription_params: dict,
        tmp_dir=".tmp",
    ):
        self.audio_input_path = audio_input_path
        self.final_audio_output_dir = final_audio_output_dir
        self.final_md_output_dir = final_md_output_dir
        self.tmp_dir = tmp_dir
        self.valid_formats = ("flac", "m4a", "mp3", "mp4", "ogg", "wav", "webm")
        self.console = Console()

        # Initialize the Transcriber with parameters to be passed to whisperx
        self.transcriber = Transcriber(
            model=transcription_params.get("model", "large-v2"),
            device_index=transcription_params.get("device_index"),
            prompt=transcription_params.get("prompt"),
            language=transcription_params.get("language"),
        )

        self.processed_audio_files = []
        self.ensure_directories()

    def ensure_directories(self):
        os.makedirs(self.final_audio_output_dir, exist_ok=True)
        os.makedirs(self.final_md_output_dir, exist_ok=True)
        os.makedirs(self.tmp_dir, exist_ok=True)

    def orchestrate(self):
        all_audio_files = self.find_audio_files(
            self.audio_input_path, self.valid_formats
        )
        audio_files_to_process = [
            f for f in all_audio_files if not self.is_processed(f)
        ]
        audio_files_to_process.sort()

        total_files = len(audio_files_to_process)
        self.console.print(f"Found {total_files} audio files to process.\n")
        self.console.log("Starting transcription...", style="bold")
        if total_files > 0:
            with Progress(
                "[progress.description]{task.description}",
                BarColumn(bar_width=40),
                TextColumn("[bold]{task.fields[file_count]}", justify="right"),
                SpinnerColumn(spinner_name="dots", style="bold green"),
                console=self.console,
            ) as progress:
                transcription_task_id = progress.add_task(
                    "", total=total_files, file_count=f"0/{total_files}"
                )
                for index, audio_file in enumerate(audio_files_to_process, start=1):
                    new_base_name = self.process_audio_file(
                        audio_file, progress, transcription_task_id
                    )
                    progress.update(
                        transcription_task_id,
                        advance=1,
                        file_count=f"{index}/{total_files}",
                    )

                    audio_lrc_pair = (
                        audio_file,
                        os.path.join(
                            self.tmp_dir, "transcriptions", f"{new_base_name}.lrc"
                        ),
                    )
                    export_markdown(
                        [audio_lrc_pair], self.tmp_dir, "data/template.md"
                    )  # Export markdown right after processing a file
            self.console.print("Transcription complete.\n", style="green bold")

            self.export()
        else:
            self.console.print("No new files to process.", style="bold yellow")

    def process_audio_file(self, audio_file, progress, task_id):
        if self.is_processed(audio_file):
            self.console.log(
                f"Audio file already processed, skipping: {audio_file}", style="yellow"
            )
            progress.update(task_id, advance=1)  # Skip but advance the progress
            return None

        start_time = datetime.now()
        print(f"Transcribing {audio_file}...")

        # Extract date and label from the audio file path
        date_str, label = self.extract_date_label(audio_file)
        base_name = os.path.splitext(os.path.basename(audio_file))[0]
        new_base_name = (
            f"{label} ({date_str})" if label else f"{base_name} ({date_str})"
        )

        # Ensure the audio file has not already been processed
        final_audio_path = os.path.join(self.final_audio_output_dir, new_base_name)
        if os.path.exists(final_audio_path):
            self.console.log(
                f"Audio file already processed, skipping: {audio_file}", style="yellow"
            )
            progress.update(task_id, advance=1)
            return None

        # Transcribe and convert to LRC
        output_dir = os.path.join(self.tmp_dir, "transcriptions")
        os.makedirs(output_dir, exist_ok=True)
        self.transcriber.call_whisperx(audio_file, output_dir)
        to_lrc(output_dir, output_dir, date_str, label)

        end_time = datetime.now()
        duration = format_duration(end_time - start_time)
        print(f"Finished processing {audio_file} in {duration}\n")

        # Track the processed audio file
        self.processed_audio_files.append((audio_file, new_base_name))

        return new_base_name

    def export(self):
        self.console.log("Starting export...", style="bold")
        total_files = len(self.processed_audio_files)
        if total_files > 0:
            # Copy audio files to their destination
            for audio_file, base_name in self.processed_audio_files:
                file_extension = os.path.splitext(audio_file)[1]
                final_name = f"{base_name}{file_extension}"
                shutil.copy(
                    audio_file, os.path.join(self.final_audio_output_dir, final_name)
                )
                print(f"Copied audio: {final_name}")

            # Copy markdown files to their destination with unique names
            for item in os.listdir(self.tmp_dir):
                src_path = os.path.join(self.tmp_dir, item)
                if item.endswith(".md"):
                    dest_path = os.path.join(self.final_md_output_dir, item)
                    dest_path = self.get_unique_filename(dest_path)
                    shutil.copy(src_path, dest_path)
            print(f"Exported markdown files to {self.final_md_output_dir}")

            self.console.print(
                f"\nFinished exporting {total_files} audio/markdown pairs.",
                style="green bold",
            )

            # Clean up the temporary directory
            shutil.rmtree(self.tmp_dir)
        else:
            self.console.print("No files to export.", style="bold yellow")

    def get_unique_filename(self, path):
        # Ensure markdown files are not overwritten
        base, ext = os.path.splitext(path)
        counter = 1
        while os.path.exists(path):
            path = f"{base} ({counter}){ext}"
            counter += 1
        return path

    def extract_date_label(self, audio_file):
        # Extract the date and label from the audio file path
        date_str = os.path.basename(os.path.dirname(audio_file))
        _, label = parse_file_details(audio_file)
        return date_str, label

    def find_audio_files(self, path, valid_formats):
        audio_files = []
        for root, _, files in os.walk(path):
            for file in files:
                if file.endswith(valid_formats):
                    audio_files.append(os.path.join(root, file))
        return audio_files

    def is_processed(self, audio_file):
        # Extract date and label from the audio file path
        date_str, label = self.extract_date_label(audio_file)
        base_name = os.path.basename(audio_file)
        file_ext = os.path.splitext(base_name)[1]
        new_base_name = (
            f"{label} ({date_str}){file_ext}"
            if label
            else f"{os.path.splitext(base_name)[0]} ({date_str}){file_ext}"
        )
        final_audio_path = os.path.join(self.final_audio_output_dir, new_base_name)
        return os.path.exists(final_audio_path)
