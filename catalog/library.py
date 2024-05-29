import os
import yaml
import sys
import shutil
import json
import hashlib
from send2trash import send2trash
from fuzzywuzzy import process as fuzzy_process
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

            from catalog.media import Voice

            if isinstance(media_object, Voice):
                media_object.set_timestamp()

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

        for date_key in [
            "date_created",
            "date_modified",
            "date_stored",
            "date_recorded",
        ]:
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

        if media_object.metadata.get("tags"):
            tags = [
                self.get_tag_name(tag["id"])
                for tag in media_object.metadata.get("tags")
            ]
            output.append(f"tags: {', '.join(tags)}")

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

    def search(
        self,
        query,
        mode="exact",
        max_results=10,
        threshold=80,
        ignore_case=True,
        full_search=False,
    ):
        def _exact_search(entry, query, results, media_id, entry_type, ignore_case):
            if "nodes" in entry:
                for index, node in enumerate(entry["nodes"]):
                    content_key = "content" if "content" in node else "text"
                    content = (
                        node[content_key].lower() if ignore_case else node[content_key]
                    )
                    if query in content:
                        locator = f"{media_id[:8]}:{entry_type}:{entry['id'][:5]}.nodes:{index}"
                        results.append((node[content_key], locator))

        def _fuzzy_search(
            entry, query, results, media_id, entry_type, threshold, ignore_case
        ):
            if "nodes" in entry:
                nodes_content = [
                    node["content"] if "content" in node else node["text"]
                    for node in entry["nodes"]
                ]
                search_results = fuzzy_process.extract(
                    query, nodes_content, limit=len(nodes_content)
                )
                for result in search_results:
                    node_index = nodes_content.index(result[0])
                    if result[1] >= threshold:
                        locator = f"{media_id[:8]}:{entry_type}:{entry['id'][:5]}.nodes:{node_index}"
                        results.append((result[0], locator))

        results = []
        entries_to_search = []

        # search recent entry (speech_data/transcript) or all entries (full_search)
        for media_object in self.media_objects:
            if full_search:
                if hasattr(media_object, "speech_data"):
                    for entry in media_object.speech_data:
                        entries_to_search.append(
                            (media_object.id, "speech_data", entry)
                        )
                if hasattr(media_object, "transcripts"):
                    for entry in media_object.transcripts:
                        entries_to_search.append(
                            (media_object.id, "transcripts", entry)
                        )
            else:
                if hasattr(media_object, "speech_data") and media_object.speech_data:
                    entries_to_search.append(
                        (media_object.id, "speech_data", media_object.speech_data[-1])
                    )
                elif hasattr(media_object, "transcripts") and media_object.transcripts:
                    entries_to_search.append(
                        (media_object.id, "transcripts", media_object.transcripts[-1])
                    )

        query = query.lower() if ignore_case else query

        for media_id, entry_type, entry in entries_to_search:
            if mode == "exact":
                _exact_search(entry, query, results, media_id, entry_type, ignore_case)
            elif mode == "fuzzy":
                _fuzzy_search(
                    entry, query, results, media_id, entry_type, threshold, ignore_case
                )

            if len(results) >= max_results:
                break

        return results[:max_results]

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

    def create_obj_pointer(self, media_object, dest_path="data/pointers"):
        def write_file(path, name, content):
            os.makedirs(path, exist_ok=True)
            with open(os.path.join(path, name), "w") as file:
                file.write(content)

        object_id = media_object.id
        name = (
            media_object.metadata.get("name")
            or media_object.metadata.get("source_filename")
            or object_id
        )
        obj_type = media_object.__class__.__name__.lower()
        date_prepared = datetime.now().isoformat()
        source_filename = media_object.metadata.get("source_filename")

        if media_object.metadata.get("tags"):
            tags = [
                self.get_tag_name(tag["id"])
                for tag in media_object.metadata.get("tags")
            ]
            tags_str = f"{f'media/{obj_type}'}, {', '.join(tags)}"
        else:
            tags_str = f"media/{obj_type}"

        frontmatter = {
            "tags": tags_str,
            "obj": object_id,
            "source_filename": source_filename,
        }

        latest_entry = None
        if media_object.speech_data:
            latest_entry = media_object.speech_data[-1]
            frontmatter["speech_data"] = latest_entry["id"]
            frontmatter["section_count"] = len(latest_entry.get("sections", []))
            frontmatter["node_count"] = len(latest_entry.get("nodes", []))
        elif media_object.transcripts:
            latest_entry = media_object.transcripts[-1]
            frontmatter["transcript"] = latest_entry["id"]
            frontmatter["node_count"] = len(latest_entry.get("nodes", []))
        frontmatter["prepared"] = date_prepared

        frontmatter_str = (
            "---\n"
            + "\n".join(
                f"{key}: {value}" for key, value in frontmatter.items() if value
            )
            + "\n---"
        )

        body = (
            media_object.get_markdown_str()
            if hasattr(media_object, "get_markdown_str")
            else ""
        )
        content = f"{frontmatter_str}\n\n{body}".strip()

        filename = f"{name}.md" if not name.endswith(".md") else name
        write_file(dest_path, filename, content)

    def create_tag_pointer(self, tag_id, tags_dir):
        tag = next((tag for tag in self.tags if tag["id"] == tag_id), None)
        if not tag:
            print(f"No tag found with ID: {tag_id}")
            return

        # skip tags with 'meta' as an ancestor
        current_tag = tag
        while current_tag.get("parents"):
            parent_id = current_tag["parents"][0]
            parent_tag = next((t for t in self.tags if t["id"] == parent_id), None)
            if parent_tag and parent_tag["name"].lower() == "meta":
                print(f"Skipping tag '{tag['name']}' as it has 'meta' as an ancestor.")
                return
            current_tag = parent_tag

        has_children = any(
            tag_id in child_tag.get("parents", []) for child_tag in self.tags
        )

        if self.count_tag_assignments(tag_id) == 0 and not has_children:
            print(
                f"Skipping tag '{tag['name']}' as it has no assignments and no children."
            )
            return

        # create tag path
        tag_path_parts = [tag["name"]]
        parent_id = tag.get("parents", [])
        while parent_id:
            parent_tag = next((t for t in self.tags if t["id"] == parent_id[0]), None)
            if parent_tag:
                tag_path_parts.insert(0, parent_tag["name"])
                parent_id = parent_tag.get("parents", [])
            else:
                break
        tag_path = os.path.join(tags_dir, *tag_path_parts[:-1])
        os.makedirs(tag_path, exist_ok=True)

        # create tag pointer alongside folder
        tag_name = tag_path_parts[-1]
        pointer_content = f"---\ntitle: {tag_name}\ntag: {tag['id']}\n---\n"
        pointer_path = os.path.join(tag_path, f"{tag_name}.md")

        try:
            with open(pointer_path, "w") as file:
                file.write(pointer_content)
            print(f"Created tag pointer for {tag_name}")
        except Exception as e:
            print(f"Error creating tag pointer for {tag_name}: {str(e)}")

        # recursively create child tags
        for child_tag in self.tags:
            if tag_id in child_tag.get("parents", []):
                self.create_tag_pointer(child_tag["id"], tags_dir)

        # create object pointers for objects tagged with the current tag
        for media_object in self.media_objects:
            if any(t["id"] == tag_id for t in media_object.metadata.get("tags", [])):
                media_type = media_object.__class__.__name__.lower()
                media_dir = os.path.join(tags_dir, "media", media_type)
                os.makedirs(media_dir, exist_ok=True)
                self.create_obj_pointer(media_object, media_dir)

    def create_pointer(self, target, dest_path="data/pointers", mode="default"):
        if mode == "quartz":
            if isinstance(target, str) and target.startswith("tag_"):
                self.create_tag_pointer(target, dest_path)
            else:
                self.create_tag_pointer(target, dest_path)
        else:
            self.create_obj_pointer(target, dest_path)

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

    def count_tag_assignments(self, tag_id):
        count = 0
        for obj in self.media_objects:
            if any(tag["id"] == tag_id for tag in obj.metadata.get("tags", [])):
                count += 1
            for entry_type in ["transcripts", "speech_data"]:
                for entry in getattr(obj, entry_type, []):
                    if any(tag["id"] == tag_id for tag in entry.get("tags", [])):
                        count += 1
        return count

    def delete_tag(self, tag_id):
        self.tags = [tag for tag in self.tags if tag["id"] != tag_id]
        for obj in self.media_objects:
            if "tags" in obj.metadata:
                obj.metadata["tags"] = [
                    tag for tag in obj.metadata["tags"] if tag["id"] != tag_id
                ]
            for entry_type in ["transcripts", "speech_data"]:
                for entry in getattr(obj, entry_type, []):
                    if "tags" in entry:
                        entry["tags"] = [
                            tag for tag in entry["tags"] if tag["id"] != tag_id
                        ]

    def rename_tag(self, tag_id, new_name):
        tag = next((tag for tag in self.tags if tag["id"] == tag_id), None)
        if tag:
            tag["name"] = new_name
        else:
            raise ValueError(f"No tag found with ID: {tag_id}")

    def add_parent_tag(self, tag_id, parent_id):
        tag = next((tag for tag in self.tags if tag["id"] == tag_id), None)
        if tag:
            if parent_id not in tag["parents"]:
                tag["parents"].append(parent_id)
        else:
            raise ValueError(f"No tag found with ID: {tag_id}")

    def remove_parent_tag(self, tag_id, parent_id):
        tag = next((tag for tag in self.tags if tag["id"] == tag_id), None)
        if tag:
            tag["parents"] = [pid for pid in tag["parents"] if pid != parent_id]
        else:
            raise ValueError(f"No tag found with ID: {tag_id}")

    def create_tag(self, name, parent=None):
        if any(tag["name"].lower() == name.lower() for tag in self.tags):
            raise ValueError(f"Tag '{name}' already exists.")
        tag_id = str(uuid.uuid4())
        tag = {
            "id": tag_id,
            "name": name,
            "parents": [parent] if parent else [],
        }
        self.tags.append(tag)
        return tag_id

    def get_tag_id(self, target):
        # check if target is a full ID
        if target in [tag["id"] for tag in self.tags]:
            return target

        # check if target is a partial ID of >= 5 characters
        if len(target) >= 5:
            partial_matches = [tag for tag in self.tags if tag["id"].startswith(target)]
            if len(partial_matches) == 1:
                return partial_matches[0]["id"]
            elif len(partial_matches) > 1:
                conflict_details = "\n".join(
                    [
                        f"{match['name']} (ID: {match['id']})"
                        for match in partial_matches
                    ]
                )
                raise ValueError(
                    f"Multiple matches found for tag '{target}':\n{conflict_details}"
                )

        # find potential matches by name/parentage
        target_parts = target.split("/")
        potential_matches = []

        for tag in self.tags:
            tag_parts = [tag["name"]]
            parent_ids = tag.get("parents", [])

            while parent_ids:
                parent_id = parent_ids[0]
                parent_tag = next((t for t in self.tags if t["id"] == parent_id), None)
                if parent_tag:
                    tag_parts.insert(0, parent_tag["name"])
                    parent_ids = parent_tag.get("parents", [])
                else:
                    break

            # check if the base name matches
            if target_parts[-1].lower() == tag_parts[-1].lower():
                potential_matches.append((tag["id"], "/".join(tag_parts)))

        if len(potential_matches) == 1:
            return potential_matches[0][0]
        elif len(potential_matches) > 1:
            conflict_details = "\n".join(
                [f"{match[1]} (ID: {match[0]})" for match in potential_matches]
            )
            raise ValueError(
                f"Multiple matches found for tag '{target}':\n{conflict_details}"
            )
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
                "date_recorded": media_object.metadata.get("date_recorded"),
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
            if key in ["date_created", "date_modified", "date_recorded"]:
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
