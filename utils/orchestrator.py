import os
import shutil
from core.transcribe import Transcriber, to_lrc
from utils.export import export_markdown, parse_file_details


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

        self.export()

    def find_audio_files(self, path, valid_formats):
        audio_files = []
        for root, _, files in os.walk(path):
            for file in files:
                if file.endswith(valid_formats):
                    audio_files.append(os.path.join(root, file))
        print(f"Found {len(audio_files)} audio files.")
        return audio_files

    def process_audio_file(self, audio_file):
        # Extract date and label from the audio file path
        date_str, label = self.extract_date_label(audio_file)
        base_name = os.path.basename(audio_file)
        file_ext = os.path.splitext(base_name)[1]
        new_base_name = (
            f"{label} ({date_str}){file_ext}"
            if label
            else f"{os.path.splitext(base_name)[0]} ({date_str}){file_ext}"
        )

        # Ensure the audio file has not already been processed
        final_audio_path = os.path.join(self.final_audio_output_dir, new_base_name)
        if os.path.exists(final_audio_path):
            print(f"Audio file already processed, skipping: {audio_file}")
            return

        # Transcribe and convert to LRC
        output_dir = os.path.join(self.tmp_dir, "transcriptions")
        os.makedirs(output_dir, exist_ok=True)
        self.transcriber.call_whisperx(audio_file, output_dir)
        to_lrc(output_dir, output_dir)

        # Find the generated LRC file
        lrc_filename = next(
            (f for f in os.listdir(output_dir) if f.endswith(".lrc")), None
        )
        if not lrc_filename:
            print(f"No LRC file generated for: {audio_file}")
            return

        lrc_file_path = os.path.join(output_dir, lrc_filename)
        audio_lrc_pair = (audio_file, lrc_file_path)
        export_markdown([audio_lrc_pair], self.tmp_dir, "data/template.md")

        # Track the processed audio file
        self.processed_audio_files.append((audio_file, new_base_name))

    def export(self):
        # Copy audio files to their destination with the new naming convention
        for audio_file, new_base_name in self.processed_audio_files:
            shutil.copy(
                audio_file, os.path.join(self.final_audio_output_dir, new_base_name)
            )

        # Copy markdown files to their destination with unique names
        for item in os.listdir(self.tmp_dir):
            src_path = os.path.join(self.tmp_dir, item)
            if item.endswith(".md"):
                dest_path = os.path.join(self.final_md_output_dir, item)
                dest_path = self.get_unique_filename(dest_path)
                shutil.copy(src_path, dest_path)

        # Clean up the temporary directory
        shutil.rmtree(self.tmp_dir)

    def get_unique_filename(self, path):
        # Ensure markdown files are not overwritten
        base, ext = os.path.splitext(path)
        counter = 1
        while os.path.exists(path):
            path = f"{base} ({counter}){ext}"
            counter += 1
        return path

    def extract_date_label(self, audio_file):
        # Extract the date and label from the audio file path
        date_str = os.path.basename(os.path.dirname(audio_file))
        _, label = parse_file_details(audio_file)
        return date_str, label
