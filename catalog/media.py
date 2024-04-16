import os
import uuid
from datetime import datetime
import tempfile
import yt_dlp
from abc import ABC, abstractmethod
from catalog.process import format_transcript
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
            "source_filename": source_filename or os.path.basename(self.file_path)
            if self.file_path
            else None,
        }

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

    @abstractmethod
    def process(self):
        pass

    def set_text(self):
        pass

    def can_transcribe(self):
        return False

    def store_processed_text(self, processed_str, source=None, label=None):
        # ensure the string doesn't already exist as a text value of any processed_text entry
        if any(processed_str == entry["text"] for entry in self.processed_text):
            raise ValueError(f"Text is already stored in processed_text for {self.id}")

        entry = {
            "id": str(uuid.uuid4()),
            "label": label,
            "source": source,
            "date_stored": datetime.now().isoformat(),
            "text": processed_str,
        }
        self.processed_text.append(entry)


class Image(MediaObject):
    def __init__(self, file_path=None, url=None, name=None, source_filename=None):
        super().__init__(file_path, url, name)

    def process(self):
        print("Processing generic image")


class Screenshot(Image):
    def __init__(self, file_path=None, url=None, name=None, source_filename=None):
        super().__init__(file_path, url, name)

    def process(self):
        print("Processing screenshot")


@can_transcribe
class Video(MediaObject):
    def __init__(self, file_path=None, url=None, name=None, source_filename=None):
        super().__init__(file_path, url, name)
        self.transcripts = []

    def process(self):
        print("Processing generic video")


@can_transcribe
class Audio(MediaObject):
    def __init__(self, file_path=None, url=None, name=None, source_filename=None):
        super().__init__(file_path, url, name)
        self.transcripts = []

    def process(self):
        print("Processing generic audio")


class Voice(Audio):
    def __init__(self, file_path=None, url=None, name=None, source_filename=None):
        super().__init__(file_path, url, name)

    def process(self):
        print("Processing voice")
