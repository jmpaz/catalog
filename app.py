import argparse
import os
import shutil
from datetime import datetime
from core.transcribe import call_whisperx, convert_to_lrc
from utils.file_utils import MarkdownExporter
from utils.logging import Logger


def process_audio_file(file_path, temp_dir, args, logger, markdown_exporter=None):
    start_time = datetime.now()

    if args.verbose:
        print(f"Transcribing {file_path}...")

    call_whisperx(
        file_path,
        temp_dir,
        output_format="srt",
        speaker_count=args.speaker_count,
        device_index=args.device_index,
        initial_prompt=args.prompt,
    )

    if args.format == "lrc":
        convert_to_lrc(temp_dir, args.output)

    if markdown_exporter:
        transcript_file = os.path.join(
            temp_dir, os.path.splitext(os.path.basename(file_path))[0] + ".lrc"
        )
        markdown_exporter.export_to_markdown(transcript_file, file_path)

    if args.relocate_files == "true":
        shutil.move(file_path, args.audio_output)

    end_time = datetime.now()
    logger.log_file_process(file_path, start_time, end_time)

    if args.verbose:
        print(f"Finished processing {file_path}. Duration: {end_time - start_time}\n")


def process_directory(directory_path, args, logger, markdown_exporter=None):
    temp_dir = "tmp" if args.format == "lrc" else args.output
    os.makedirs(temp_dir, exist_ok=True)

    for filename in os.listdir(directory_path):
        file_path = os.path.join(directory_path, filename)
        process_audio_file(file_path, temp_dir, args, logger, markdown_exporter)

    if args.format == "lrc":
        shutil.rmtree(temp_dir)


def transcribe(args, logger):
    print(f"Transcribe command received for {args.input_path}. Starting...\n")
    logger.start_session(args)

    if not os.path.exists(args.input_path):
        raise FileNotFoundError(f"Input path {args.input_path} does not exist.")
    elif os.path.isdir(args.input_path) and not os.listdir(args.input_path):
        raise FileNotFoundError(f"Input directory {args.input_path} is empty.")

    if not os.path.exists(args.output):
        os.makedirs(args.output)
    if args.export and not os.path.exists(args.audio_output):
        os.makedirs(args.audio_output)

    markdown_exporter = None
    if args.export:
        markdown_exporter = MarkdownExporter(
            args.template, args.output, args.audio_output
        )

    if os.path.isdir(args.input_path):
        process_directory(args.input_path, args, logger, markdown_exporter)
    else:
        temp_dir = "tmp" if args.format == "lrc" else args.output
        os.makedirs(temp_dir, exist_ok=True)
        process_audio_file(args.input_path, temp_dir, args, logger, markdown_exporter)
        if args.format == "lrc":
            shutil.rmtree(temp_dir)

    logger.end_session()


def export(args, logger):
    print(f"Export command received for {args.input_dir}. Starting...\n")

    if not os.path.exists(args.input_dir):
        raise FileNotFoundError(f"Input directory {args.input_dir} does not exist.")

    if not os.path.exists(args.output):
        os.makedirs(args.output)
    if not os.path.exists(args.audio_output):
        os.makedirs(args.audio_output)

    markdown_exporter = MarkdownExporter(args.template, args.output, args.audio_output)

    for filename in os.listdir(args.input_dir):
        if filename.endswith(".lrc"):
            base_name, _ = os.path.splitext(filename)
            lrc_file = os.path.join(args.input_dir, filename)

            # Find the associated audio file (any extension)
            associated_file = None
            for potential_file in os.listdir(args.input_dir):
                if potential_file.startswith(base_name) and potential_file != filename:
                    associated_file = os.path.join(args.input_dir, potential_file)
                    break

            if associated_file and os.path.exists(associated_file):
                markdown_exporter.export_md(lrc_file, associated_file)
            else:
                print(f"No associated audio file found for {lrc_file}")


def main():
    parser = argparse.ArgumentParser(
        description="CLI for audio transcription and processing."
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output.")
    subparsers = parser.add_subparsers(help="sub-command help", dest="command")

    # Transcribe parser
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
        "--audio_output",
        default="data/audio",
        help="Output directory for audio files. Default is 'data/audio'.",
    )
    parser_transcribe.add_argument(
        "--relocate_files",
        choices=["true", "false"],
        default="true",
        help="Whether to move transcribed audio files to the audio output directory upon completion. Accepts 'true' or 'false'; default is 'true'.",
    )
    parser_transcribe.add_argument(
        "-f",
        "--format",
        choices=["srt", "json", "lrc"],
        default="srt",
        help="Output format: 'srt', 'json', 'lrc'.",
    )
    parser_transcribe.add_argument(
        "--speaker_count", type=int, help="Set minimum and maximum number of speakers."
    )
    parser_transcribe.add_argument(
        "--device_index", type=int, help="Index of the device to use."
    )
    parser_transcribe.add_argument("--prompt", type=str, help="Initial prompt to use.")
    parser_transcribe.add_argument(
        "--export", action="store_true", help="Enable exporting to markdown format."
    )
    parser_transcribe.add_argument(
        "--template", help="Path to the markdown template file."
    )
    parser_transcribe.set_defaults(func=transcribe)

    # Export parser
    parser_export = subparsers.add_parser(
        "export", help="Export LRC files to markdown format."
    )
    parser_export.add_argument(
        "input_dir", help="Input directory containing LRC files."
    )
    parser_export.add_argument(
        "--output",
        default="data/processed",
        help="Output directory for Markdown files. Default is 'data/processed'.",
    )
    parser_export.add_argument(
        "--audio_output",
        default="data/audio",
        help="Output directory for relocated audio files. Default is 'data/audio'.",
    )
    parser_export.add_argument(
        "--template", required=True, help="Path to the markdown template file."
    )
    parser_export.set_defaults(func=export)

    args = parser.parse_args()

    if args.verbose:
        print("Verbose mode enabled.")

    logger = Logger("logs/log.json")

    if args.command is None:
        parser.print_help()
    else:
        args.func(args, logger)
        logger.save_log()


if __name__ == "__main__":
    main()
