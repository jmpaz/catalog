import os
from abc import ABC, abstractmethod


class MediaObject(ABC):
    def __init__(self, file_path=None):
        self.file_path = file_path
        self.file_content = None
        if file_path:
            self.import_file(file_path)

    def import_file(self, file_path):
        if os.path.isfile(file_path):
            with open(file_path, "rb") as file:
                self.file_content = file.read()
        else:
            raise FileNotFoundError(f"No file found at {file_path}")

    def get_details(self):
        import_path = self.file_path if self.file_path else None
        file_size = len(self.file_content) if self.file_content else 0
        return {"import_path": import_path, "file_size": file_size}

    @abstractmethod
    def process(self):
        pass


class Audio(MediaObject):
    def process(self):
        print("Processing generic audio")


class Voice(Audio):
    def __init__(self, file_path=None):
        super().__init__(file_path)
        self.transcripts = []

    def can_transcribe(self):
        return True

    def process(self):
        print("Processing voice")


class Music(Audio):
    def process(self):
        print("Processing music")


class Video(MediaObject):
    def __init__(self, file_path=None):
        super().__init__(file_path)
        self.transcripts = []

    def can_transcribe(self):
        return True

    def process(self):
        print("Processing generic video")


class Image(MediaObject):
    def process(self):
        print("Processing generic image")


class Screenshot(Image):
    def process(self):
        print("Processing screenshot")


class Art(Image):
    def process(self):
        print("Processing art")


class Photo(Image):  # e.g. from camera roll
    def process(self):
        print("Processing photo")
