import os
import shutil
from core.transcribe import Transcriber, to_lrc
from utils.export import export_markdown


class Orchestrator:
    def __init__(
        self,
        audio_input_path,
        final_audio_output_dir,
        final_md_output_dir,
        tmp_dir=".tmp",
    ):
        self.audio_input_path = audio_input_path
        self.final_audio_output_dir = final_audio_output_dir
        self.final_md_output_dir = final_md_output_dir
        self.tmp_dir = tmp_dir
        self.valid_formats = ("flac", "m4a", "mp3", "mp4", "ogg", "wav", "webm")
        self.transcriber = Transcriber()
        self.processed_audio_files = []
        self.ensure_directories()

    def ensure_directories(self):
        os.makedirs(self.final_audio_output_dir, exist_ok=True)
        os.makedirs(self.final_md_output_dir, exist_ok=True)
        os.makedirs(self.tmp_dir, exist_ok=True)

    def orchestrate(self):
        audio_files = self.find_audio_files(self.audio_input_path, self.valid_formats)

        for audio_file in audio_files:
            self.process_audio_file(audio_file)

        self.export_and_cleanup()

    def find_audio_files(self, path, valid_formats):
        audio_files = []
        for root, _, files in os.walk(path):
            for file in files:
                if file.endswith(valid_formats):
                    audio_files.append(os.path.join(root, file))
        print(f"Found {len(audio_files)} audio files.")
        return audio_files

    def process_audio_file(self, audio_file):
        # Transcribe and convert to LRC
        output_dir = os.path.join(self.tmp_dir, "transcriptions")
        os.makedirs(output_dir, exist_ok=True)
        self.transcriber.call_whisperx(audio_file, output_dir)
        to_lrc(output_dir, output_dir)

        # Prepare for markdown export
        lrc_file = os.path.splitext(os.path.basename(audio_file))[0] + ".lrc"
        lrc_file_path = os.path.join(output_dir, lrc_file)
        audio_lrc_pair = (audio_file, lrc_file_path)
        export_markdown([audio_lrc_pair], self.tmp_dir, "data/template.md")

        # Track the processed audio file
        self.processed_audio_files.append(audio_file)

    def export_and_cleanup(self):
        # Copy audio files to their destination
        for audio_file in self.processed_audio_files:
            shutil.copy(audio_file, self.final_audio_output_dir)

        # Copy markdown files to their destination
        for item in os.listdir(self.tmp_dir):
            src_path = os.path.join(self.tmp_dir, item)
            if item.endswith(".md"):
                shutil.copy(src_path, self.final_md_output_dir)

        # Clean up the temporary directory
        shutil.rmtree(self.tmp_dir)
