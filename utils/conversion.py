import os
import re


def srt_timestamp_to_lrc(timestamp):
    # SRT format: '00:01:02,500' -> LRC format: '[01:02.00]'
    match = re.match(r"(\d+):(\d+):(\d+),\d+", timestamp)
    if match:
        return f"[{match.group(2)}:{match.group(3)}.0]"
    return "[00:00.0]"


def convert_srt_to_lrc(srt_file_path, lrc_file_path):
    with open(srt_file_path, "r") as srt, open(lrc_file_path, "w") as lrc:
        lines = srt.readlines()
        for i, line in enumerate(lines):
            if "-->" in line:
                start_time, _ = line.split(" --> ")
                lrc_timestamp = srt_timestamp_to_lrc(start_time.strip())
                if i + 1 < len(lines):
                    text_content = lines[i + 1].strip()
                    lrc.write(f"{lrc_timestamp}  {text_content}\n")

    os.remove(srt_file_path)


def to_lrc(input_dir, output_dir):
    for srt_file in os.listdir(input_dir):
        if srt_file.endswith(".srt"):
            srt_path = os.path.join(input_dir, srt_file)
            lrc_path = os.path.join(output_dir, os.path.splitext(srt_file)[0] + ".lrc")
            convert_srt_to_lrc(srt_path, lrc_path)


def insert_lrc(lrc_file_path, audio_filename, template_path):
    """
    Injects the entire LRC content into a Markdown template.
    The template file's contents are left untouched, except:
    - the insertion point, denoted by `LRC_DEST` in the template, is replaced with the LRC content
    - the file name, denoted by `source [[FILE_NAME.ext]]` (within brackets), is replaced with the audio file name and extension

    The resultant Markdown-formatted string is returned.
    """
    with open(template_path, "r") as template:
        template_content = template.read()
        with open(lrc_file_path, "r") as lrc:
            lrc_content = lrc.read()
            return template_content.replace("LRC_DEST", lrc_content).replace(
                "[[FILE_NAME.ext]]", f"[[{audio_filename}]]"
            )
