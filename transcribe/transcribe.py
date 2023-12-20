import subprocess


def call_whisperx(
    input_path,
    output_dir,
    model="large-v2",
    language="en",
    output_format="srt",
    speaker_count=None,
    device_index=None,
):
    cmd = [
        "whisperx",
        input_path,
        "--model",
        model,
        "--language",
        language,
        "--output_format",
        output_format,
    ]

    if speaker_count:
        cmd.extend(
            ["--min_speakers", str(speaker_count), "--max_speakers", str(speaker_count)]
        )

    if device_index is not None:
        cmd.extend(["--device_index", str(device_index)])

    # Add output directory argument
    cmd.extend(["--output_dir", output_dir])

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"An error occurred while running whisperx: {e}")
