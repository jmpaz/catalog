import os
import sys
import shutil
import json
import hashlib
from datetime import datetime
from catalog.media import MediaObject


class Library:
    def __init__(
        self,
        library_path="~/.config/catalog/library.json",
        datastore_path="~/.local/share/catalog/data",
    ):
        self.library_path = os.path.expanduser(library_path)
        self.datastore_path = os.path.expanduser(datastore_path)
        self.media_objects = []
        self.load_library()

    def import_media_object(
        self,
        file_path=None,
        media_object_class=None,
        name=None,
        url=None,
        auto=False,
        make_copy=True,
    ):
        if auto:
            ext_map = {
                "Voice": [".mp3", ".wav", ".flac", ".m4a", ".ogg"],
                "Video": [".mp4", ".mkv", ".webm", ".avi", ".mov"],
            }
            # set media_object_class to the first class that supports the extension
            ext = os.path.splitext(file_path)[1].lower()
            for obj_class, exts in ext_map.items():
                if ext in exts:
                    media_object_class = getattr(
                        sys.modules["catalog.media"], obj_class
                    )
                    break
            else:
                raise ValueError(f"Unsupported file type: {ext}")

        if media_object_class and issubclass(media_object_class, MediaObject):
            md5_hash = self.compute_md5_hash(file_path)
            existing_object = self.fetch_object_by_hash(md5_hash)
            if existing_object:
                print(
                    f"Media object with hash {md5_hash} already exists. Returning the existing object."
                )
                return existing_object

            source_filename = os.path.basename(file_path) if file_path else None
            media_object = media_object_class(
                file_path=file_path, url=url, name=name, source_filename=source_filename
            )
            media_object.md5_hash = md5_hash

            if make_copy and file_path:  # make a copy of the file in the datastore
                os.makedirs(self.datastore_path, exist_ok=True)
                file_ext = os.path.splitext(file_path)[1]
                target_path = os.path.join(
                    self.datastore_path, f"{media_object.id}{file_ext}"
                )
                shutil.copy2(file_path, target_path)
                media_object.file_path = target_path

            self.media_objects.append(media_object)
            self.save_library()
            return media_object
        else:
            raise ValueError("media_object_class must be a subclass of MediaObject")

    def compute_md5_hash(self, file_path):
        if file_path and os.path.isfile(file_path):
            with open(file_path, "rb") as file:
                file_content = file.read()
                md5_hash = hashlib.md5(file_content).hexdigest()
                return md5_hash
        return None

    def fetch_object_by_hash(self, md5_hash):
        for media_object in self.media_objects:
            if media_object.md5_hash == md5_hash:
                return media_object
        return None

    def load_library(self):
        if os.path.exists(self.library_path):
            with open(self.library_path, "r") as file:
                library_data = json.load(file)
                self.media_objects = [
                    self.deserialize_object(obj_data)
                    for obj_data in library_data["media_objects"]
                ]
        else:
            print(
                f"Library file not found at {self.library_path}. Starting with an empty library."
            )

    def save_library(self):
        os.makedirs(os.path.dirname(self.library_path), exist_ok=True)
        library_data = {
            "media_objects": [
                self.serialize_object(media_object)
                for media_object in self.media_objects
            ]
        }
        with open(self.library_path, "w") as file:
            json.dump(library_data, file, indent=2)

    def query(self, media_objects=None):
        if media_objects is None:
            raise ValueError("No MediaObjects provided")
        elif not isinstance(media_objects, list):
            media_objects = [media_objects]

        for media_object in media_objects:
            # print object attributes
            for attr, value in media_object.__dict__.items():
                if (
                    not attr.startswith("_")
                    and not callable(value)
                    and value is not None
                    and (not isinstance(value, (list, str)) or value)
                ):
                    if attr == "file_content":
                        print(f"{attr}: (exists)")
                    else:
                        print(f"{attr}: {value}")

            print()  # newline

    def fetch(self, ids=None):
        """Fetch media objects by ID."""
        output = []

        if ids:
            output.extend([obj for obj in self.media_objects if obj.id[:5] in ids])

        return output

    def _print_value(self, value, indent=2):
        if isinstance(value, dict):
            for key, val in value.items():
                print(f"{' ' * indent}{key}:")
                self._print_value(val, indent + 2)
        elif isinstance(value, list):
            for i, item in enumerate(value, start=1):
                print(f"{' ' * indent}Item {i}:")
                self._print_value(item, indent + 2)
        else:
            print(f"{' ' * indent}{value}")

    def create_pointer(self, media_object, dest_path="data/pointers"):
        id = media_object.id
        name = media_object.name if media_object.name else None
        obj_type = media_object.__class__.__name__
        frontmatter = f"""---
id:
- {id}
tags:
- media/{obj_type.lower()}
---"""
        body = media_object.text if media_object.text else ""
        content = f"{frontmatter}\n{body}" if body else frontmatter

        filename = name if name else id

        self.write_file(dest_path, filename, content)

    @staticmethod
    def write_file(path, name, content):
        path = path
        os.makedirs(path, exist_ok=True)
        with open(f"{path}/{name}.md", "w") as file:
            file.write(content)

    def serialize_object(self, media_object):
        serialized_data = {
            "id": media_object.id,
            "metadata": {
                "name": media_object.metadata.get("name"),
                "url": media_object.metadata.get("url"),
                "date_created": media_object.metadata.get("date_created").isoformat()
                if media_object.metadata.get("date_created")
                else None,
                "date_modified": media_object.metadata.get("date_modified").isoformat()
                if media_object.metadata.get("date_modified")
                else None,
                "date_stored": media_object.metadata.get("date_stored"),
                "source_filename": media_object.metadata.get("source_filename"),
            },
            "file_path": media_object.file_path,
            "md5_hash": media_object.md5_hash,
            "text": media_object.text,
            "processed_text": media_object.processed_text,
            "transcripts": media_object.transcripts
            if hasattr(media_object, "transcripts")
            else [],
            "class_name": media_object.__class__.__name__,
            "module_name": media_object.__class__.__module__,
        }
        return serialized_data

    def deserialize_object(self, serialized_data):
        class_name = serialized_data["class_name"]
        module_name = serialized_data.get(
            "module_name", "catalog.media"
        )  # default to 'catalog.media' if not specified

        try:
            module = __import__(module_name, fromlist=[class_name])
            media_object_class = getattr(module, class_name)
        except (ImportError, AttributeError):
            raise ValueError(
                f"Failed to import class '{class_name}' from module '{module_name}'"
            )

        media_object = media_object_class(
            file_path=serialized_data["file_path"],
            url=serialized_data["metadata"].get("url"),
            name=serialized_data["metadata"].get("name"),
            # source_filename=serialized_data["metadata"].get("source_filename"),  # handled in MediaObject constructor
        )
        media_object.id = serialized_data["id"]
        media_object.metadata["date_created"] = (
            datetime.fromisoformat(serialized_data["metadata"].get("date_created"))
            if serialized_data["metadata"].get("date_created")
            else None
        )
        media_object.metadata["date_modified"] = (
            datetime.fromisoformat(serialized_data["metadata"].get("date_modified"))
            if serialized_data["metadata"].get("date_modified")
            else None
        )
        media_object.metadata["date_stored"] = serialized_data["metadata"].get(
            "date_stored"
        )
        media_object.md5_hash = serialized_data["md5_hash"]
        media_object.text = serialized_data["text"]
        media_object.processed_text = serialized_data.get("processed_text", [])
        if hasattr(media_object, "transcripts"):
            media_object.transcripts = serialized_data["transcripts"]
        return media_object


class Job:
    def __init__(self):
        self.tasks = []

    def add_task(self, task):
        if not callable(task):
            raise ValueError("task must be a callable")
        self.tasks.append(task)

    def execute(self, media_object):
        for task in self.tasks:
            task(media_object)
