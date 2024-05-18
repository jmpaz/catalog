import os
import yaml
import sys
import shutil
import json
import hashlib
from send2trash import send2trash
from fuzzywuzzy import fuzz
from datetime import datetime
from catalog.media import MediaObject
from catalog.utils import fetch_subtarget_entry
from contextualize.tokenize import call_tiktoken
import uuid


class Library:
    def __init__(
        self,
        library_path="~/.config/catalog/library.json",
        datastore_path="~/.local/share/catalog/data",
    ):
        self.library_path = os.path.expanduser(library_path)
        self.datastore_path = os.path.expanduser(datastore_path)
        self.media_objects = []
        self.tags = []
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
        def _handle_chat():
            from catalog.media import Chat

            if media_object_class == Chat and file_path.lower().endswith(
                (".yaml", ".yml")
            ):
                chat_metadata, participants, messages = _prepare_chat_data(file_path)
                media_object = Chat(
                    file_path=file_path,
                    name=name,
                    chat_metadata=chat_metadata,
                    participants=participants,
                    messages=messages,
                    source_filename=os.path.basename(file_path),
                )
                media_object.md5_hash = self.compute_md5_hash(file_path)

                existing_object = self.fetch_object_by_hash(media_object.md5_hash)
                if existing_object:
                    print(
                        f"Chat object with hash {media_object.md5_hash} already exists. Returning the existing object."
                    )
                    return existing_object
                else:
                    self.media_objects.append(media_object)

                self.save_library()
                return media_object

        def _prepare_chat_data(yaml_file):
            """Prepare chat data for storage."""
            with open(yaml_file, "r") as file:
                data = yaml.safe_load(file)

            excerpt_data = data["excerpt"]

            # store chat metadata ('meta') as a single dict of key-value pairs
            chat_metadata = {}
            for item in excerpt_data:
                if "meta" in item:
                    for key in item["meta"]:
                        chat_metadata.update(key)

            # store participants as a dict of 'name': 'id' pairs
            participants = next(
                item["participants"] for item in excerpt_data if "participants" in item
            )
            participants = {
                list(p.keys())[0]: list(p.values())[0] for p in participants
            }

            messages = next(
                item["messages"] for item in excerpt_data if "messages" in item
            )

            return chat_metadata, participants, messages

        _handle_chat()

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

            source_filename = os.path.basename(file_path) if file_path else None
            media_object = media_object_class(
                file_path=file_path, url=url, name=name, source_filename=source_filename
            )
            media_object.md5_hash = md5_hash

            existing_object = self.fetch_object_by_hash(md5_hash)
            if existing_object:
                print(
                    f"Media object with hash {md5_hash} already exists. Returning the existing object."
                )
                return existing_object
            else:
                self.media_objects.append(media_object)

            if make_copy and file_path:  # make a copy of the file in the datastore
                os.makedirs(self.datastore_path, exist_ok=True)
                file_ext = os.path.splitext(file_path)[1]
                target_path = os.path.join(
                    self.datastore_path, f"{media_object.id}{file_ext}"
                )
                shutil.copy2(file_path, target_path)
                media_object.file_path = target_path

            self.save_library()
            return media_object
        else:
            raise ValueError("media_object_class must be a subclass of MediaObject")

    def remove_media_object(self, media_object, delete_file=False):
        self.media_objects = [
            obj for obj in self.media_objects if obj.id != media_object.id
        ]
        if delete_file and media_object.file_path:
            send2trash(media_object.file_path)

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
                    for obj_data in library_data.get("media_objects", [])
                ]
                self.tags = library_data.get("tags", [])
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
            ],
            "tags": self.tags,
        }
        with open(self.library_path, "w") as file:
            json.dump(library_data, file, indent=2)

    def query(self, media_object):
        if not isinstance(media_object, MediaObject):
            raise ValueError("Invalid media object")

        output = []
        output.append(f"id: {media_object.id}")

        name = media_object.metadata.get("name")
        if name:
            output.append(f"name: {name}")

        output.append(f"object_class: {media_object.__class__.__name__}")

        for date_key in ["date_stored", "date_created", "date_modified"]:
            date_value = media_object.metadata.get(date_key)
            if date_value:
                output.append(f"{date_key}: {date_value}")

        source_filename = media_object.metadata.get("source_filename")
        if source_filename:
            output.append(f"source_filename: {source_filename}")

        if media_object.file_path:
            output.append(f"file_path: {media_object.file_path}")

        if media_object.text:
            token_count = call_tiktoken(media_object.text)["count"]
            output.append(f"text: Exists ({token_count} tokens)")

        if media_object.processed_text:
            output.append(f"processed_text: {len(media_object.processed_text)} entries")

        if hasattr(media_object, "transcripts"):
            output.append(f"transcripts: {len(media_object.transcripts)} entries")

        if hasattr(media_object, "speech_data"):
            output.append(f"speech_data: {len(media_object.speech_data)} entries")

        if hasattr(media_object, "participants"):
            output.append(f"participants: {len(media_object.participants)} entries")
        if hasattr(media_object, "messages"):
            output.append(f"messages: {len(media_object.messages)} entries")
        if (
            hasattr(media_object, "chat_metadata")
            and len(media_object.chat_metadata) > 0
        ):
            output.append(f"chat_metadata: {len(media_object.chat_metadata)} entries")

        return "\n".join(output)

    def fetch(self, ids=None):
        """Fetch media objects by ID."""
        output = []

        if ids:
            for id in ids:
                for obj in self.media_objects:
                    if obj.id.startswith(id):
                        output.append(obj)
                        break
                else:
                    raise ValueError(f"No media object found with ID: {id}")

        return output

    def fetch_entry(self, media_object_id, entry_type, entry_id):
        """Fetch a specific entry from a media object."""
        media_object = next(
            (obj for obj in self.media_objects if obj.id.startswith(media_object_id)),
            None,
        )
        if media_object:
            entries = getattr(media_object, entry_type, [])
            entry = next((e for e in entries if e["id"].startswith(entry_id)), None)
            if entry:
                return media_object, entry
            else:
                raise ValueError(
                    f"No {entry_type[:-1]} entry found with ID: {entry_id}"
                )
        else:
            raise ValueError(f"No media object found with ID: {media_object_id}")

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
        name = media_object.metadata.get("name")
        if not name:
            name = media_object.metadata.get("source_filename", "").split(".")[0]
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

    def get_tag_name(self, tag_id):
        tag = next((tag for tag in self.tags if tag["id"] == tag_id), None)
        if not tag:
            raise ValueError(f"No tag found with ID: {tag_id}")

        parts = [tag["name"]]
        while tag.get("parents"):
            parent_id = tag["parents"][0]
            tag = next((t for t in self.tags if t["id"] == parent_id), None)
            if tag:
                parts.insert(0, tag["name"])
            else:
                break

        return "/".join(parts)

    def create_tag(self, name, parent=None):
        tag_id = str(uuid.uuid4())
        tag = {
            "id": tag_id,
            "name": name,
            "parents": [parent] if parent else [],
        }
        self.tags.append(tag)
        return tag_id

    def get_tag_id(self, target):
        if target in [tag["id"] for tag in self.tags]:
            return target

        target_parts = target.split("/")
        best_match = None
        best_ratio = 0

        for tag in self.tags:
            tag_parts = [tag["name"]] + [
                self.get_tag_name(parent) for parent in tag.get("parents", [])
            ]
            if len(target_parts) != len(tag_parts):
                continue

            ratio = fuzz.ratio(" ".join(target_parts), " ".join(tag_parts))
            if ratio > best_ratio:
                best_match = tag["id"]
                best_ratio = ratio

        if best_ratio >= 80:
            return best_match
        else:
            raise ValueError(f"No close match found for tag: {target}")

    def tag_object(self, media_object, tag=None, tag_str=None, source="user"):
        if tag_str:
            tag_id = self.get_tag_id(tag_str)

        if "tags" not in media_object.metadata:
            media_object.metadata["tags"] = []

        tag_exists = any(tag_id == tag["id"] for tag in media_object.metadata["tags"])
        if tag_exists:
            raise ValueError(f"Tag {tag_id} already assigned to obj {media_object.id}")

        tag_data = {
            "id": tag_id,
            "date_assigned": datetime.now().isoformat(),
            "source": source,
        }
        media_object.metadata["tags"].append(tag_data)

    def untag_object(self, media_object, tag_id):
        if "tags" in media_object.metadata:
            media_object.metadata["tags"] = [
                tag for tag in media_object.metadata["tags"] if tag["id"] != tag_id
            ]

    def untag_entry(self, media_object, entry_type, entry_id, tag_id):
        entry = fetch_subtarget_entry(media_object, entry_type, entry_id)
        if "tags" in entry:
            entry["tags"] = [tag for tag in entry["tags"] if tag["id"] != tag_id]

    def tag_entry(
        self, media_object, entry_type, entry_id, tag=None, tag_str=None, source="user"
    ):
        entry = fetch_subtarget_entry(media_object, entry_type, entry_id)

        if tag_str:
            tag_id = self.get_tag_id(tag_str)

        if "tags" not in entry:
            entry["tags"] = []

        tag_exists = any(tag_id == tag["id"] for tag in entry["tags"])
        if tag_exists:
            raise ValueError(f"Tag {tag_id} already assigned to entry {entry_id}")

        tag_data = {
            "id": tag_id,
            "date_assigned": datetime.now().isoformat(),
            "source": source,
        }
        entry["tags"].append(tag_data)

    def serialize_object(self, media_object):
        serialized_data = {
            "id": media_object.id,
            "metadata": {
                "name": media_object.metadata.get("name"),
                "url": media_object.metadata.get("url"),
                "date_created": (
                    media_object.metadata.get("date_created").isoformat()
                    if isinstance(media_object.metadata.get("date_created"), datetime)
                    else media_object.metadata.get("date_created")
                ),
                "date_modified": (
                    media_object.metadata.get("date_modified").isoformat()
                    if isinstance(media_object.metadata.get("date_modified"), datetime)
                    else media_object.metadata.get("date_modified")
                ),
                "date_stored": media_object.metadata.get("date_stored"),
                "source_filename": media_object.metadata.get("source_filename"),
                "tags": media_object.metadata.get("tags", []),
            },
            "chat_metadata": getattr(media_object, "chat_metadata", {})
            if hasattr(media_object, "chat_metadata")
            else {},
            "file_path": media_object.file_path,
            "md5_hash": media_object.md5_hash,
            "text": media_object.text,
            "processed_text": media_object.processed_text,
            "class_name": media_object.__class__.__name__,
            "module_name": media_object.__class__.__module__,
        }

        # store attributes not already serialized
        for attr_name in dir(media_object):
            if not attr_name.startswith("__") and attr_name not in serialized_data:
                attr_value = getattr(media_object, attr_name)
                if isinstance(attr_value, (str, int, float, bool, list, dict)):
                    serialized_data[attr_name] = attr_value

        return serialized_data

    def deserialize_object(self, serialized_data):
        class_name = serialized_data["class_name"]
        module_name = serialized_data.get("module_name", "catalog.media")

        try:
            module = __import__(module_name, fromlist=[class_name])
            media_object_class = getattr(module, class_name)
        except (ImportError, AttributeError):
            raise ValueError(
                f"Failed to import class '{class_name}' from module '{module_name}'"
            )

        if class_name == "Chat":
            media_object = media_object_class(
                name=serialized_data["metadata"]["name"],
                chat_metadata=serialized_data.get("chat_metadata", {}),
                participants=serialized_data.get("participants", []),
                messages=serialized_data.get("messages", []),
                source_filename=serialized_data["metadata"]["source_filename"],
            )
        else:
            media_object = media_object_class(file_path=serialized_data["file_path"])

        media_object.id = serialized_data["id"]
        media_object.md5_hash = serialized_data["md5_hash"]

        # set metadata
        for key, value in serialized_data["metadata"].items():
            if key in ["date_created", "date_modified"]:
                media_object.metadata[key] = (
                    datetime.fromisoformat(value)
                    if value and isinstance(value, str)
                    else value
                )
            else:
                media_object.metadata[key] = value

        # set text
        media_object.text = serialized_data["text"]
        media_object.processed_text = serialized_data["processed_text"]

        # set other attributes
        for attr_name, attr_value in serialized_data.items():
            if hasattr(media_object, attr_name):
                setattr(media_object, attr_name, attr_value)

        return media_object
