import argparse
import os
import shutil
from datetime import datetime
from rich.console import Console
from rich.progress import SpinnerColumn
from rich.progress import Progress, TextColumn, BarColumn
from core.transcribe import Transcriber
from utils.logging import Logger
from utils.conversion import to_lrc


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
        file_list = sorted(os.listdir(directory_path))
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

        if self.args.format == "lrc":
            to_lrc(self.temp_dir, self.args.output)
            shutil.rmtree(self.temp_dir)

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


class ArgParser:
    def __init__(self):
        self.console = Console()
        self.parser = argparse.ArgumentParser(
            description="CLI for audio transcription and processing."
        )
        self._add_arguments()

    def _add_arguments(self):
        self.parser.add_argument(
            "--verbose", action="store_true", help="Enable verbose output."
        )
        subparsers = self.parser.add_subparsers(help="sub-command help", dest="command")

        parser_transcribe = subparsers.add_parser(
            "transcribe", help="Transcribe audio files."
        )
        parser_transcribe.add_argument(
            "input_path", help="Path to the audio file or directory to transcribe."
        )
        parser_transcribe.add_argument(
            "-o",
            "--output",
            default="data/processed",
            help="Output directory for the files. Default is 'data/processed'.",
        )
        parser_transcribe.add_argument(
            "--relocate_files",
            choices=["true", "false"],
            default="true",
            help="Whether to move transcribed audio files to the output directory upon completion. Accepts 'true' or 'false'; default is 'true'.",
        )
        parser_transcribe.add_argument(
            "-f",
            "--format",
            choices=["srt", "json", "lrc"],
            default="srt",
            help="Output format: 'srt', 'json', 'lrc'.",
        )
        parser_transcribe.add_argument(
            "--speaker_count",
            type=int,
            help="Set minimum and maximum number of speakers.",
        )
        parser_transcribe.add_argument(
            "--device_index", type=int, help="Index of the device to use."
        )
        parser_transcribe.add_argument(
            "--prompt", type=str, help="Initial prompt to use."
        )
        parser_transcribe.set_defaults(func=self.handle_transcription)

    def handle_transcription(self, args, logger):
        audio_handler = AudioHandler(args, logger, self.console)
        audio_handler.transcribe()

    def parse_args(self):
        return self.parser.parse_args()


def main():
    arg_parser = ArgParser()
    args = arg_parser.parse_args()

    if args.verbose:
        print("Verbose mode enabled.")

    if args.command is None:
        arg_parser.parser.print_help()
    else:
        logger = Logger("logs/log.json")
        arg_parser.handle_transcription(args, logger)


if __name__ == "__main__":
    main()
