import os
import re
import shutil


class MarkdownExporter:
    def __init__(self, template_path, md_output_folder, audio_output_folder):
        self.template_path = template_path
        self.md_output_folder = md_output_folder
        self.audio_output_folder = audio_output_folder

    @staticmethod
    def sanitize_filename(filename):
        # Replace invalid characters with an en dash
        return re.sub(r"[^\w\s-]", "–", filename)

    @staticmethod
    def extract_timestamp(filename):
        # Extract timestamp from filename
        # Examples: '20-15-59' or 'Saturday at 12:12 PM'
        match = re.search(r"(\d{1,2}):(\d{2})\s*(AM|PM)", filename, re.IGNORECASE)
        if match:
            return f"{match.group(1)}:{match.group(2)}{match.group(3).lower()}"
        return None

    def check_file_existence(self, validated_filename):
        target_file_path = os.path.join(
            self.md_output_folder, f"{validated_filename}.md"
        )
        return os.path.exists(target_file_path)

    def create_markdown_file(
        self, lrc_content, associated_file, extracted_time, validated_filename
    ):
        # Read template file
        with open(self.template_path, "r") as template_file:
            content = template_file.read()

        associated_file_name = os.path.basename(associated_file)

        # Replace placeholders
        content = content.replace("[[sample-audio.wav]]", f"[[{associated_file_name}]]")
        content = content.replace("[00:00.0]  [not added]", lrc_content)

        if extracted_time:
            content = re.sub(r"created:.*", f"created_time: {extracted_time}", content)

        # Write to new Markdown file
        md_file_path = os.path.join(self.md_output_folder, f"{validated_filename}.md")
        with open(md_file_path, "w") as md_file:
            md_file.write(content)

    def export_md(self, transcript_file, associated_file):
        validated_filename = self.sanitize_filename(
            os.path.splitext(associated_file)[0]
        )
        if self.check_file_existence(validated_filename):
            print(f"File {validated_filename}.md already exists.")
            return

        extracted_time = self.extract_timestamp(associated_file)

        with open(transcript_file, "r") as file:
            lrc_content = file.read()

        self.create_markdown_file(
            lrc_content, associated_file, extracted_time, validated_filename
        )

        # Move the associated audio file
        shutil.move(
            associated_file,
            os.path.join(self.audio_output_folder, os.path.basename(associated_file)),
        )
