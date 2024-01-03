import argparse
import os
import shutil
from datetime import datetime
from core.transcribe import Transcriber
from utils.logging import Logger


class ArgParser:
    def __init__(self):
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
        parser_transcribe.set_defaults(func=self.transcribe)

    def parse_args(self):
        return self.parser.parse_args()

    def transcribe(self, args, logger):
        print(f"Transcribe command received for {args.input_path}. Starting...\n")
        logger.start_session(args)

        if not os.path.exists(args.input_path):
            raise FileNotFoundError(f"Input path {args.input_path} does not exist.")
        elif os.path.isdir(args.input_path) and not os.listdir(args.input_path):
            raise FileNotFoundError(f"Input directory {args.input_path} is empty.")

        if not os.path.exists(args.output):
            os.makedirs(args.output)

        transcriber = Transcriber(device_index=args.device_index)

        if os.path.isdir(args.input_path):
            self.process_directory(args.input_path, args, logger, transcriber)
        else:
            temp_dir = "tmp" if args.format == "lrc" else args.output
            os.makedirs(temp_dir, exist_ok=True)
            self.process_audio_file(
                args.input_path, temp_dir, args, logger, transcriber
            )
            if args.format == "lrc":
                shutil.rmtree(temp_dir)

        logger.end_session()

    def process_audio_file(self, file_path, temp_dir, args, logger, transcriber):
        start_time = datetime.now()

        if args.verbose:
            print(f"Transcribing {file_path}...")

        transcriber.call_whisperx(
            file_path,
            temp_dir,
            output_format="srt",
            speaker_count=args.speaker_count,
            initial_prompt=args.prompt,
        )

        if args.format == "lrc":
            Transcriber.convert_to_lrc(temp_dir, args.output)
        if args.relocate_files == "true":
            shutil.move(file_path, args.output)

        end_time = datetime.now()
        logger.log_file_process(file_path, start_time, end_time)

        if args.verbose:
            print(
                f"Finished processing {file_path}. Duration: {end_time - start_time}\n"
            )

    def process_directory(self, directory_path, args, logger, transcriber):
        temp_dir = "tmp" if args.format == "lrc" else args.output
        os.makedirs(temp_dir, exist_ok=True)

        for filename in os.listdir(directory_path):
            file_path = os.path.join(directory_path, filename)
            self.process_audio_file(file_path, temp_dir, args, logger, transcriber)

        if args.format == "lrc":
            shutil.rmtree(temp_dir)


def main():
    arg_parser = ArgParser()
    args = arg_parser.parse_args()

    if args.verbose:
        print("Verbose mode enabled.")

    if args.command is None:
        arg_parser.parser.print_help()
    else:
        logger = Logger("logs/log.json")
        args.func(args, logger)
        logger.save_log()


if __name__ == "__main__":
    main()
