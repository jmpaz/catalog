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


def extract_lrc_content(lrc_file_path):
    """
    Extracts the LRC content from a file and returns it as a string.
    """
    if not os.path.exists(lrc_file_path):
        raise FileNotFoundError(f"LRC file not found: {lrc_file_path}")
    else:
        with open(lrc_file_path, "r") as target_lrc:
            lrc_str = target_lrc.read()
            return lrc_str


def prepare_markdown(template_src, lrc_str, filename_str):
    """
    Injects LRC content into a Markdown template. Returns the resultant Markdown string.
    """
    if not os.path.exists(template_src):
        raise FileNotFoundError(f"Template file not found: {template_src}")
    else:
        template = open(template_src, "r").read()
        markdown_content = template.replace(
            "[[FILE_NAME.ext]]", f"[[{filename_str}]]"
        ).replace("LRC_DEST", lrc_str)
    return markdown_content
