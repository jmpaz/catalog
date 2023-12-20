import argparse
from transcribe.transcribe import call_whisperx


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Transcribe audio and convert to various formats."
    )
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
        "-f",
        "--format",
        choices=["srt", "json"],
        default=None,
        help="Output format: 'srt', 'json'. Default is 'srt'.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()
    call_whisperx(
        args.input_path,
        args.output,
        output_format=args.format if args.format else "srt",
    )
