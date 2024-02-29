import subprocess
import re
import os


class Transcriber:
    def __init__(self, model="large-v2", language=None, device_index=None, prompt=None):
        self.model = model
        self.language = language
        self.device_index = device_index
        self.prompt = prompt

    def call_whisperx(
        self,
        input_path,
        output_dir,
        output_format="srt",
        speaker_count=None,
        initial_prompt=None,
        verbose=False,
    ):
        cmd = [
            "whisperx",
            input_path,
            "--model",
            self.model,
            "--output_format" "",
            output_format,
            "--output_dir",
            output_dir,
        ]

        if self.language:
            cmd += ["--language", self.language]

        if speaker_count:
            cmd += [
                "--min_speakers",
                str(speaker_count),
                "--max_speakers",
                str(speaker_count),
            ]

        if initial_prompt or self.prompt:
            cmd += ["--initial_prompt", initial_prompt or self.prompt]

        if self.device_index is not None:
            cmd += ["--device_index", str(self.device_index)]

        try:
            process = subprocess.run(
                cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )

            if verbose:
                print(process.stdout.decode())

        except subprocess.CalledProcessError as e:
            print(f"An error occurred while running whisperx: {e.stderr.decode()}")


def to_lrc(input_dir, output_dir, date_str=None, label=None):
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

    for srt_file in os.listdir(input_dir):
        if srt_file.endswith(".srt"):
            base_name = os.path.splitext(srt_file)[0]
            file_ext = ".lrc"
            if date_str:
                new_base_name = (
                    f"{label} ({date_str}){file_ext}"
                    if label
                    else f"{base_name} ({date_str}){file_ext}"
                )
            else:
                new_base_name = (
                    f"{label}{file_ext}" if label else f"{base_name}{file_ext}"
                )
            srt_path = os.path.join(input_dir, srt_file)
            lrc_path = os.path.join(output_dir, new_base_name)
            convert_srt_to_lrc(srt_path, lrc_path)
