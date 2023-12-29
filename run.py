import argparse
import os
import shutil
from core.transcribe import call_whisperx, convert_to_lrc


def transcribe(args):
    def process_audio_file(file_path, temp_dir, args):
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
        if args.relocate_files == "true":
            shutil.move(file_path, args.output)

    def process_directory(directory_path, args):
        temp_dir = "tmp" if args.format == "lrc" else args.output
        os.makedirs(temp_dir, exist_ok=True)

        for filename in os.listdir(directory_path):
            file_path = os.path.join(directory_path, filename)
            process_audio_file(file_path, temp_dir, args)

        if args.format == "lrc":
            shutil.rmtree(temp_dir)

    if not os.path.exists(args.input_path):
        raise FileNotFoundError(f"Input path {args.input_path} does not exist.")
    elif os.path.isdir(args.input_path) and not os.listdir(args.input_path):
        raise FileNotFoundError(f"Input directory {args.input_path} is empty.")

    if not os.path.exists(args.output):
        os.makedirs(args.output)

    if os.path.isdir(args.input_path):
        process_directory(args.input_path, args)
    else:
        temp_dir = "tmp" if args.format == "lrc" else args.output
        os.makedirs(temp_dir, exist_ok=True)
        process_audio_file(args.input_path, temp_dir, args)
        if args.format == "lrc":
            shutil.rmtree(temp_dir)


def main():
    parser = argparse.ArgumentParser(
        description="CLI for audio transcription and processing."
    )
    subparsers = parser.add_subparsers(help="sub-command help", dest="command")

    # Subparser for the 'transcribe' command
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
        "--speaker_count", type=int, help="Set minimum and maximum number of speakers."
    )
    parser_transcribe.add_argument(
        "--device_index", type=int, help="Index of the device to use."
    )
    parser_transcribe.add_argument("--prompt", type=str, help="Initial prompt to use.")
    parser_transcribe.set_defaults(func=transcribe)

    # Parse the arguments
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
    else:
        args.func(args)


if __name__ == "__main__":
    main()
