import os
import argparse
from rich.console import Console
from core.orchestrator import Orchestrator
from utils.logging import Logger
from utils.file_handling import AudioHandler, sync_files
from utils.ingest import PixelExtractor


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
            "-x",
            "--export",
            action="store_true",
            help="Whether to prepare & export markdown files along with corresponding audio files. Expects a directory structure 'YYYY-MM-DD/HH-MM-SS.ext' for the input files.",
        )
        parser_transcribe.add_argument(
            "--audio_dest",
            help="Output directory for exported audio files.",
        )
        parser_transcribe.add_argument(
            "--md_dest",
            help="Output directory for exported markdown files.",
        )
        parser_transcribe.add_argument(
            "--speaker_count",
            type=int,
            help="Set minimum and maximum number of speakers.",
        )
        parser_transcribe.add_argument(
            "--prompt",
            type=str,
            help="Initial prompt (e.g. sentence, glossary) to use during inference.",
        )
        parser_transcribe.add_argument(
            "--device_index", type=int, help="GPU index to use for transcription."
        )
        parser_transcribe.add_argument(
            "--relocate_files",
            choices=["true", "false"],
            default="true",
            help="When not exporting, move the processed files to the output directory instead of copying them.",
        )
        parser_transcribe.add_argument(
            "--format",
            choices=["srt", "json", "lrc"],
            default="srt",
            help="Output format (not used when exporting): 'srt', 'json', 'lrc'.",
        )
        parser_transcribe.add_argument(
            "--language",
            type=str,
            help="Language code (e.g. 'en', 'es') to use for transcription.",
        )
        parser_transcribe.set_defaults(func=self.handle_transcription)

        # File synchronization (e.g. from Google Drive)
        parser_pull = subparsers.add_parser(
            "pull", help="Synchronize files/folders to a local directory."
        )
        parser_pull.add_argument(
            "source_dirs", nargs="+", help="List of source directories to synchronize."
        )
        parser_pull.add_argument(
            "-d",
            "--destination",
            default="data/imports",
            help="Destination directory for the files. Default is 'data/imports'.",
        )
        parser_pull.set_defaults(func=self.handle_pull)

        # Ingest from supported sources
        parser_ingest = subparsers.add_parser(
            "ingest", help="Ingest audio files for processing."
        )
        parser_ingest.add_argument(
            "source_dir", help="Source directory containing audio files."
        )
        parser_ingest.add_argument(
            "target_dir", help="Target directory for processed audio files."
        )
        parser_ingest.add_argument(
            "--move", action="store_true", help="Move files instead of copying."
        )
        parser_ingest.set_defaults(func=self.handle_ingest)

    def handle_ingest(self, args, logger):
        logger.start_session(args)

        # Initialize PixelExtractor with source and target directories
        extractor = PixelExtractor(
            args.source_dir, args.target_dir, mode="move" if args.move else "sync"
        )
        self.console.log("Starting ingest...\n")

        summary = extractor.process_directory()  # Store ingest results
        if summary["processed"] > 0:
            self.console.log(f"Successfully processed {summary['processed']} files.")
        if summary["skipped"] > 0:
            self.console.log(f"Skipped {summary['skipped']} files.")
        if summary["processed"] == 0 and summary["skipped"] == 0:
            self.console.log("No files were extracted.", style="bold yellow")

        logger.end_session()
        logger.save_log()

    def handle_pull(self, args, logger):
        logger.start_session(args)

        sync_files(args.source_dirs, args.destination)

        logger.end_session()
        logger.save_log()

    def handle_transcription(self, args, logger):
        if args.export:
            self.handle_export(args, logger)
        else:
            audio_handler = AudioHandler(args, logger, self.console)
            audio_handler.transcribe()

    def handle_export(self, args, logger):
        logger.start_session(args)

        # Set output directories
        if not args.audio_dest:
            args.audio_dest = os.path.join(
                args.output, os.path.basename(args.input_path)
            )
        if not args.md_dest:
            args.md_dest = args.audio_dest

        # Collect relevant parameters for orchestration
        transcription_params = {
            "speaker_count": args.speaker_count,
            "device_index": args.device_index,
            "prompt": args.prompt,
            "language": args.language,
        }

        orchestrator = Orchestrator(
            audio_input_path=args.input_path,
            final_audio_output_dir=args.audio_dest,
            final_md_output_dir=args.md_dest,
            transcription_params=transcription_params,
        )

        orchestrator.orchestrate()

        logger.end_session()
        logger.save_log()

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
        # Call the appropriate handler based on the command
        if hasattr(args, "func"):
            args.func(args, logger)
        else:
            arg_parser.parser.print_help()
            print("\nNo valid command provided.")


if __name__ == "__main__":
    main()
