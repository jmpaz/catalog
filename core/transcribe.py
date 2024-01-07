import subprocess


class Transcriber:
    def __init__(self, model="large-v2", language="en", device_index=None):
        self.model = model
        self.language = language
        self.device_index = device_index

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
            "--output_format",
            output_format,
            "--output_dir",
            output_dir,
            "--language",
            self.language,
        ]

        if speaker_count:
            cmd += [
                "--min_speakers",
                str(speaker_count),
                "--max_speakers",
                str(speaker_count),
            ]

        if initial_prompt:
            cmd += ["--initial_prompt", initial_prompt]

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
