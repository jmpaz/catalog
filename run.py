import argparse
import os
import shutil
from transcribe.transcribe import call_whisperx, convert_to_lrc


def parse_arguments():
    parser = argparse.ArgumentParser(description="Transcribe audio with WhisperX.")
    parser.add_argument(
        "input_path", help="Path to the audio file or directory to transcribe."
    )
    parser.add_argument(
        "-o",
        "--output",
        default="data/processed",
        help="Output directory for the files. Default is 'data/processed'.",
    )
    parser.add_argument(
        "--relocate_files",
        action="store_true",
        default=True,
        help="Move transcribed audio files to the output directory upon completion.",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["srt", "json", "lrc"],
        default="srt",
        help="Output format: 'srt', 'json', 'lrc'.",
    )
    parser.add_argument(
        "--speaker_count",
        type=int,
        help="Set minimum and maximum number of speakers.",
    )
    parser.add_argument(
        "--device_index",
        type=int,
        help="Index of the device to use.",
    )
    return parser.parse_args()


def process_audio_file(file_path, temp_dir, args):
    call_whisperx(
        file_path,
        temp_dir,
        output_format="srt",
        speaker_count=args.speaker_count,
        device_index=args.device_index,
    )
    if args.format == "lrc":
        convert_to_lrc(temp_dir, args.output)
    if args.relocate_files:
        shutil.move(file_path, args.output)


def process_directory(directory_path, args):
    temp_dir = "tmp" if args.format == "lrc" else args.output
    os.makedirs(temp_dir, exist_ok=True)

    for filename in os.listdir(directory_path):
        file_path = os.path.join(directory_path, filename)
        process_audio_file(file_path, temp_dir, args)

    if args.format == "lrc":
        shutil.rmtree(temp_dir)


if __name__ == "__main__":
    args = parse_arguments()

    if not os.path.exists(args.input_path):
        raise FileNotFoundError(f"Input path {args.input_path} does not exist.")

    if os.path.isdir(args.input_path):
        process_directory(args.input_path, args)
    else:
        temp_dir = "tmp" if args.format == "lrc" else args.output
        os.makedirs(temp_dir, exist_ok=True)
        process_audio_file(args.input_path, temp_dir, args)
        if args.format == "lrc":
            shutil.rmtree(temp_dir)
