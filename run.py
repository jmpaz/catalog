import sys
import os
import json
import argparse
from transcribe import transcribe_audio
from transcribe.format import hf_pipeline_to_srt, hf_pipeline_to_lrc


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Transcribe audio and convert to various formats."
    )
    parser.add_argument("file_path", help="Path to the audio file to transcribe.")
    parser.add_argument(
        "-o",
        "--output",
        default="data/processed",
        help="Output directory for the files. Default is 'data/processed'.",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["srt", "json", "lrc"],
        default=None,
        help="Output format: 'srt', 'json', 'lrc'. Default is 'srt' and 'json'.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()

    if not os.path.exists(args.file_path):
        print(f"The file {args.file_path} does not exist.")
        sys.exit(1)

    if not os.path.exists(args.output):
        os.makedirs(args.output)

    try:
        # Transcribe audio
        json_result = transcribe_audio(args.file_path)

        base_file_name = os.path.basename(args.file_path).rsplit(".", 1)[0]
        json_output_file = os.path.join(args.output, base_file_name + ".json")
        srt_output_file = os.path.join(args.output, base_file_name + ".srt")
        lrc_output_file = os.path.join(args.output, base_file_name + ".lrc")

        # Save JSON
        if args.format in [None, "json"]:
            with open(json_output_file, "w") as f:
                json.dump(json_result, f, indent=4)
            print(f"JSON output saved to {json_output_file}")

        # Convert to SRT and save
        if args.format in [None, "srt"]:
            hf_pipeline_to_srt(json_result, output_file=srt_output_file)
            print(f"SRT output saved to {srt_output_file}")

        # Save LRC
        if args.format == "lrc":
            hf_pipeline_to_lrc(json_result, output_file=lrc_output_file)
            print(f"LRC output saved to {lrc_output_file}")

    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)
