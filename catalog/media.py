import os
import uuid
from datetime import datetime
import tempfile
import yt_dlp
from abc import ABC
from catalog.process import format_transcript
from catalog.utils import format_speech_data, format_transcript_nodes
from contextualize.reference import process_text as delimit_text


def can_transcribe(cls):
    def set_text(self, format_sensitivity=0.02, format_interval=40):
        if self.processed_text:
            latest_processed = self.processed_text[-1]
            self.text = latest_processed["text"]
        elif self.transcripts:
            latest_transcript = self.transcripts[-1]
            self.text = format_transcript(
                latest_transcript,
                format_sensitivity,
                timestamp_interval=format_interval,
            )

    cls.set_text = set_text
    cls.can_transcribe = lambda self: True
    return cls


class MediaObject(ABC):
    def __init__(self, file_path=None, url=None, name=None, source_filename=None):
        self.id = str(uuid.uuid4())
        self.file_path = os.path.abspath(file_path) if file_path else None
        self.text = ""
        self.processed_text = []
        self.metadata = {
            "name": name,
            "url": url,
            "date_created": None,
            "date_modified": None,
            "date_stored": None,
            "source_filename": source_filename or os.path.basename(self.file_path)
            if self.file_path
            else None,
        }

        if not self.metadata["date_stored"]:
            self.metadata["date_stored"] = datetime.now().isoformat()

        if self.file_path:
            self.import_file(self.file_path)
        elif url:
            self.import_url(url)

    def import_file(self, file_path):
        if os.path.isfile(file_path):
            self.metadata["date_created"], self.metadata["date_modified"] = (
                self.get_file_dates(file_path)
            )
        else:
            raise FileNotFoundError(f"No file found at {file_path}")

    def import_url(self, url):
        with tempfile.TemporaryDirectory() as temp_dir:
            ydl_opts = {
                "outtmpl": os.path.join(temp_dir, "%(title)s.%(ext)s"),
                "quiet": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                path = ydl.prepare_filename(info)
                self.metadata["date_created"], self.metadata["date_modified"] = (
                    self.get_file_dates(path)
                )
                self.file_path = path

    def remove_entry(self, entry_type, entry_id):
        if entry_type == "transcripts":
            original_length = len(self.transcripts)
            self.transcripts = [
                entry
                for entry in self.transcripts
                if not entry["id"].startswith(entry_id)
            ]
            if original_length == len(self.transcripts):
                raise ValueError(
                    f"No transcript entry found with ID starting with: {entry_id}"
                )
        elif entry_type == "processed_text":
            original_length = len(self.processed_text)
            self.processed_text = [
                entry
                for entry in self.processed_text
                if not entry["id"].startswith(entry_id)
            ]
            if original_length == len(self.processed_text):
                raise ValueError(
                    f"No processed text entry found with ID starting with: {entry_id}"
                )
        else:
            raise ValueError(f"Invalid entry type: {entry_type}")

    def get_delimited_text(self, format="md"):
        """
        Delimit the object's text content in the specified format.

        Args:
            format (str): The format to use for delimiting the text content. Supports "md" (default) and "xml".
            - "md" will wrap the text in a Markdown code block.
            - "xml" will wrap the text in XML tags.

        Returns:
            str: A string containing the text content wrapped according to the specified format.
        """
        if format != "md" and format != "xml":
            raise ValueError(f"Unsupported format '{format}'; must be 'md' or 'xml'")
        if self.text:
            label = f"{self.name}.md" if self.name else "markdown"
            return delimit_text(self.text, format=format, label=label)
        else:
            raise ValueError(f"{self.id} has no text to delimit")

    @staticmethod
    def get_file_dates(file_path):
        if os.path.isfile(file_path):
            stat = os.stat(file_path)
            date_created = datetime.fromtimestamp(stat.st_ctime)
            date_modified = datetime.fromtimestamp(stat.st_mtime)
            return date_created, date_modified
        else:
            return None, None

    def set_text(self):
        pass

    def can_transcribe(self):
        return False

    def export_text(self, format="md"):
        if format not in ["md", "sexp"]:
            raise ValueError("Unsupported format. Choose 'md' or 'sexp'.")

        if format == "md":
            output = self.get_markdown_str()
        elif format == "sexp":
            output = self.get_sexp_str()

        if output == "":
            raise ValueError("No text data available to export.")

        return output

    def get_markdown_str(self):
        """Return a Markdown string representation of the object's text content."""
        raise NotImplementedError("Not available for this object type.")

    def get_sexp_str(self):
        """Return an S-expression string representation of the object's text content."""
        raise NotImplementedError("Not yet implemented.")


class Image(MediaObject):
    def __init__(self, file_path=None, url=None, name=None, source_filename=None):
        super().__init__(file_path, url, name)


class Screenshot(Image):
    def __init__(self, file_path=None, url=None, name=None, source_filename=None):
        super().__init__(file_path, url, name)


@can_transcribe
class Video(MediaObject):
    def __init__(self, file_path=None, url=None, name=None, source_filename=None):
        super().__init__(file_path, url, name)
        self.transcripts = []
        self.speech_data = []

    def get_markdown_str(self, minimal=True):
        if self.speech_data:
            return format_speech_data([self.speech_data[-1]], minimal)
        elif self.transcripts:
            return format_transcript_nodes([self.transcripts[-1]], minimal)
        else:
            return f"# {self.metadata.get('name', 'Unnamed Video')}\n\nNo transcription available."


@can_transcribe
class Audio(MediaObject):
    def __init__(self, file_path=None, url=None, name=None, source_filename=None):
        super().__init__(file_path, url, name)
        self.transcripts = []
        self.speech_data = []

    def get_markdown_str(self, minimal=True):
        if self.speech_data:
            return format_speech_data([self.speech_data[-1]], minimal)
        elif self.transcripts:
            return format_transcript_nodes([self.transcripts[-1]], minimal)
        else:
            return f"# {self.metadata.get('name', 'Unnamed Audio')}\n\nNo transcription available."


class Voice(Audio):
    def __init__(self, file_path=None, url=None, name=None, source_filename=None):
        super().__init__(file_path, url, name)


class Chat(MediaObject):
    def __init__(
        self,
        file_path=None,
        url=None,
        name=None,
        source_filename=None,
        metadata=None,
        chat_metadata=None,
        participants=None,
        messages=None,
    ):
        super().__init__(file_path, url, name, source_filename)
        self.metadata.update(
            {item.get("key"): item.get("value") for item in metadata}
            if metadata
            else {}
        )
        self.chat_metadata = chat_metadata or {}
        self.participants = participants or []
        self.messages = messages or []
