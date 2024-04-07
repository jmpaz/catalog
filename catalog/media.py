import os
import uuid
from datetime import datetime
import tempfile
import yt_dlp
from abc import ABC, abstractmethod
from catalog.process import format_transcript


def can_transcribe(cls):
    def set_text(self):
        if self.transcripts:
            latest_transcript = self.transcripts[-1]
            if "processed" in latest_transcript:
                self.text = latest_transcript["processed"]
            else:
                self.text = format_transcript(
                    latest_transcript, sensitivity=0.02, timestamp_interval=40
                )

    cls.set_text = set_text
    cls.can_transcribe = lambda self: True
    return cls


class MediaObject(ABC):
    def __init__(self, file_path=None, url=None, name=None):
        self.id = str(uuid.uuid4())
        self.name = name
        self.file_path = file_path
        self.date_created = None
        self.date_modified = None
        self.url = url
        self.text = ""
        self.file_content = None

        if file_path:
            self.import_file(file_path)
        elif url:
            self.import_url(url)

    def import_file(self, file_path):
        if os.path.isfile(file_path):
            with open(file_path, "rb") as file:
                self.file_content = file.read()
            self.date_created, self.date_modified = self.get_file_dates(file_path)
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
                self.file_path = ydl.prepare_filename(info)

                # Read the downloaded file into memory
                with open(self.file_path, "rb") as file:
                    self.file_content = file.read()
                self.date_created, self.date_modified = self.get_file_dates(
                    self.file_path
                )

    def get_details(self):
        import_path = self.file_path if self.file_path else None
        file_size = len(self.file_content) if self.file_content else 0
        return {"import_path": import_path, "file_size": file_size}
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


@can_transcribe
class Audio(MediaObject):
    def __init__(self, file_path=None, url=None, name=None):
        super().__init__(file_path, url, name)
        self.transcripts = []

    def process(self):
        print("Processing generic audio")


class Voice(Audio):
    def __init__(self, file_path=None, url=None, name=None):
        super().__init__(file_path, url, name)

    def process(self):
        print("Processing voice")


class Music(Audio):
    def __init__(self, file_path=None, url=None, name=None):
        super().__init__(file_path, url, name)

    def process(self):
        print("Processing music")


@can_transcribe
class Video(MediaObject):
    def __init__(self, file_path=None, url=None, name=None):
        super().__init__(file_path, url, name)
        self.transcripts = []

    def process(self):
        print("Processing generic video")


class Image(MediaObject):
    def __init__(self, file_path=None, url=None, name=None):
        super().__init__(file_path, url, name)

    def process(self):
        print("Processing generic image")


class Screenshot(Image):
    def __init__(self, file_path=None, url=None, name=None):
        super().__init__(file_path, url, name)

    def process(self):
        print("Processing screenshot")


class Art(Image):
    def __init__(self, file_path=None, url=None, name=None):
        super().__init__(file_path, url, name)

    def process(self):
        print("Processing art")


class Photo(Image):
    def __init__(self, file_path=None, url=None, name=None):
        super().__init__(file_path, url, name)

    def process(self):
        print("Processing photo")
