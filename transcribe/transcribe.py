import subprocess
import os
import re


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
        "--output_format",
        output_format,
        "--output_dir",
        output_dir,
    ]

    if language:
        cmd += ["--language", language]

    if speaker_count:
        cmd += [
            "--min_speakers",
            str(speaker_count),
            "--max_speakers",
            str(speaker_count),
        ]

    if device_index is not None:
        cmd += ["--device_index", str(device_index)]

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"An error occurred while running whisperx: {e}")


def srt_timestamp_to_lrc(timestamp):
    # SRT format: '00:01:02,500' -> LRC format: '[01:02.00]'
    match = re.match(r"(\d+):(\d+):(\d+),\d+", timestamp)
    if match:
        return f"[{match.group(2)}:{match.group(3)}.0]"
    return "[00:00.0]"


def convert_to_lrc(temp_dir, output_dir):
    for srt_file in os.listdir(temp_dir):
        if srt_file.endswith(".srt"):
            srt_path = os.path.join(temp_dir, srt_file)
            lrc_path = os.path.join(output_dir, os.path.splitext(srt_file)[0] + ".lrc")

            with open(srt_path, "r") as srt, open(lrc_path, "w") as lrc:
                lines = srt.readlines()
                for i, line in enumerate(lines):
                    if "-->" in line:
                        start_time, _ = line.split(" --> ")
                        lrc_timestamp = srt_timestamp_to_lrc(start_time.strip())
                        # Check for text in the next line
                        if i + 1 < len(lines):
                            text_content = lines[i + 1].strip()
                            lrc.write(f"{lrc_timestamp}  {text_content}\n")
