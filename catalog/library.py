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
                self.groups = [
                    self.deserialize_group(group_data)
                    for group_data in library_data.get("groups", [])
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
            ],
            "tags": self.tags,
            "groups": [self.serialize_group(group) for group in self.groups],
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

        groups = []
        for group in self.groups:
            if any(obj.id == media_object.id for obj in group.objects):
                groups.append(group)
        if groups:
            output.append(f"groups: {', '.join([group.name for group in groups])}")

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

    def fetch_group(self, group_identifier):
        # check if identifier is an ID
        group = next(
            (group for group in self.groups if group.id.startswith(group_identifier)),
            None,
        )
        if group:
            return group

        # check if identifier is a name
        potential_matches = [
            group
            for group in self.groups
            if group.name and group.name.lower() == group_identifier.lower()
        ]

        if len(potential_matches) == 1:
            return potential_matches[0]
        elif len(potential_matches) > 1:
            conflict_details = "\n".join(
                [f"{match.name} (ID: {match.id})" for match in potential_matches]
            )
            raise ValueError(
                f"Multiple matches found for group '{group_identifier}':\n{conflict_details}"
            )
        else:
            raise ValueError(f"No group found with identifier: {group_identifier}")

    def query_group(self, group_id):
        group = self.fetch_group(group_id)
        if not group:
            raise ValueError(f"No group found with ID: {group_id}")

        output = [
            f"id: {group.id}",
            f"name: {group.name if group.name else 'untitled'}",
            f"created_by: {group.created_by}",
            f"date_created: {group.date_created}",
            f"description: {group.description[:40]}",
        ]

        if group.objects:
            object_details = []
            for obj in group.objects:
                name = obj.metadata.get("name")
                source_filename = obj.metadata.get("source_filename", "Unnamed")
                if name:
                    display_name = name
                else:
                    display_name = source_filename
                object_details.append(f"{obj.id[:5]} ({display_name})")
            output.append(f"objects: {', '.join(object_details)}")

        if group.groups:
            subgroup_details = [
                f"{subgroup.name if subgroup.name else 'untitled'} ({subgroup.id[:6]})"
                for subgroup in group.groups
            ]
            output.append(f"subgroups: {', '.join(subgroup_details)}")

        if group.tags:
            tags = [self.get_tag_name(tag_id) for tag_id in group.tags]
            output.append(f"tags: {', '.join(tags)}")

        return "\n".join(output)

    def delete_group(self, group_id):
        group = self.fetch_group(group_id)
        if not group:
            raise ValueError(f"No group found with ID: {group_id}")

        # unassign as parent of any subgroups
        for subgroup in self.groups:
            if group in subgroup.groups:
                subgroup.groups.remove(group)

        # remove group from library
        self.groups = [g for g in self.groups if g.id != group_id]
        self.save_library()

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

    def create_obj_pointer(
        self, media_object, dest_path="data/pointers", flatten_excess=False
    ):
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

        if hasattr(media_object, "speech_data") and media_object.speech_data:
            latest_entry = media_object.speech_data[-1]
            frontmatter.update(
                {
                    "speech_data": latest_entry["id"],
                    "section_count": len(latest_entry.get("sections", [])),
                    "node_count": len(latest_entry.get("nodes", [])),
                }
            )
        elif hasattr(media_object, "transcripts") and media_object.transcripts:
            latest_entry = media_object.transcripts[-1]
            frontmatter.update(
                {
                    "transcript": latest_entry["id"],
                    "node_count": len(latest_entry.get("nodes", [])),
                }
            )

        frontmatter["prepared"] = date_prepared

        frontmatter_str = (
            "---\n"
            + "\n".join(
                f"{key}: {value}" for key, value in frontmatter.items() if value
            )
            + "\n---"
        )

        try:
            body = media_object.get_markdown_str(flatten_excess=flatten_excess)
        except NotImplementedError:
            body = ""

        content = f"{frontmatter_str}\n\n{body}".strip()

        filename = f"{name}.md" if not name.endswith(".md") else name
        write_file(dest_path, filename, content)

    def create_tag_pointer(self, tag_id, tags_dir):
        def write_pointer_file(pointer_path, content):
            try:
                with open(pointer_path, "w") as file:
                    file.write(content)
                print(
                    f"Created pointer for {os.path.basename(pointer_path).replace('.md', '')}"
                )
            except Exception as e:
                print(
                    f"Error creating pointer for {os.path.basename(pointer_path).replace('.md', '')}: {str(e)}"
                )

        def create_parent_pointers(tag_path_parts, tags_dir, tag_id):
            parent_tag_path = tags_dir
            for part in tag_path_parts[:-1]:
                parent_tag_path = os.path.join(parent_tag_path, part)
                parent_pointer_path = os.path.join(tags_dir, f"{part}.md")
                if not os.path.exists(parent_pointer_path):
                    parent_pointer_content = f"---\ntitle: {part}\nid: {tag_id}\n---\n"
                    write_pointer_file(parent_pointer_path, parent_pointer_content)

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

        # create tag pointers
        tag_name = tag_path_parts[-1]
        pointer_content = f"---\ntitle: {tag_name}\nid: {tag['id']}\n---\n"
        if tag.get("description"):
            pointer_content += f"\n{tag['description']}\n"
        pointer_path = os.path.join(tag_path, f"{tag_name}.md")
        write_pointer_file(pointer_path, pointer_content)
        create_parent_pointers(tag_path_parts, tags_dir, tag_id)

        # creater pointers for child tags
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

    def create_group_pointer(self, group, groups_dir):
        def get_group_name(group_id):
            group = next((g for g in self.groups if g.id == group_id), None)
            if group:
                return group.name if group.name else "untitled"
            else:
                return None

        os.makedirs(groups_dir, exist_ok=True)

        group_name = group.name if group.name else "untitled"
        parent_names = [
            self.get_group_name(parent.id)
            for parent in group.groups
            if parent.id != group.id
        ]

        frontmatter = {"title": group_name, "group": group.id}

        if parent_names:
            frontmatter["parents"] = [f"[[{name}]]" for name in parent_names]

        if group.description:
            body = group.description
        else:
            body = ""

        frontmatter_str = (
            "---\n" + yaml.dump(frontmatter, default_flow_style=False) + "---\n"
        )
        content = f"{frontmatter_str}\n{body}"

        pointer_path = os.path.join(groups_dir, f"{group_name}.md")

        with open(pointer_path, "w") as file:
            file.write(content)

        print(f"Created group pointer for {group_name}")
        return content

    def fetch_all_tagged_objects(self, library, tag_id):
        tagged_objects = []
        tagged_objects.extend(
            [
                obj
                for obj in library.media_objects
                if any(t["id"] == tag_id for t in obj.metadata.get("tags", []))
            ]
        )
        for child_tag in library.tags:
            if tag_id in child_tag.get("parents", []):
                tagged_objects.extend(
                    self.fetch_all_tagged_objects(library, child_tag["id"])
                )
        return tagged_objects

    def create_pointer(
        self, target, dest_path="data/pointers", mode="default", flatten_excess=False
    ):
        processed_groups = set()

        def process_group(group):
            group_dir = os.path.join(dest_path, "groups")
            if group.id not in processed_groups:
                self.create_group_pointer(group, group_dir)
                processed_groups.add(group.id)
                for subgroup in group.groups:
                    process_group(subgroup)
                    for obj in subgroup.objects:
                        media_dir = os.path.join(
                            dest_path, "media", obj.__class__.__name__.lower()
                        )
                        self.create_obj_pointer(
                            obj, media_dir, flatten_excess=flatten_excess
                        )

        if isinstance(target, Group):
            process_group(target)
            for obj in target.objects:
                media_dir = os.path.join(
                    dest_path, "media", obj.__class__.__name__.lower()
                )
                self.create_obj_pointer(obj, media_dir, flatten_excess=flatten_excess)
        elif isinstance(target, str) and target.startswith("tag_"):
            self.create_tag_pointer(target, dest_path)
            for obj in self.fetch_all_tagged_objects(self, target):
                media_type = obj.__class__.__name__.lower()
                media_dir = os.path.join(dest_path, "media", media_type)
                self.create_obj_pointer(obj, media_dir, flatten_excess=flatten_excess)
        elif isinstance(target, str):
            self.create_tag_pointer(target, dest_path)
            for obj in self.fetch_all_tagged_objects(self, target):
                media_type = obj.__class__.__name__.lower()
                media_dir = os.path.join(dest_path, "media", media_type)
                self.create_obj_pointer(obj, media_dir, flatten_excess=flatten_excess)
        else:
            media_type = target.__class__.__name__.lower()
            media_dir = os.path.join(dest_path, "media", media_type)
            self.create_obj_pointer(target, media_dir, flatten_excess=flatten_excess)

    def update_pointer(self, pointer_path):
        with open(pointer_path, "r") as file:
            content = file.read()

        frontmatter, body = content.split("---", 2)[1:]
        frontmatter_lines = frontmatter.strip().split("\n")
        metadata = {
            line.split(": ")[0]: line.split(": ")[1] for line in frontmatter_lines
        }

        if "obj" in metadata:
            obj_id = metadata["obj"]
            media_object = next(
                (obj for obj in self.media_objects if obj.id == obj_id), None
            )
            if media_object:
                new_frontmatter = {
                    "tags": metadata.get("tags"),
                    "obj": obj_id,
                    "source_filename": media_object.metadata.get("source_filename"),
                    "prepared": metadata.get("prepared"),
                }

                if hasattr(media_object, "speech_data") and media_object.speech_data:
                    latest_entry = media_object.speech_data[-1]
                    new_frontmatter.update(
                        {
                            "speech_data": latest_entry["id"],
                            "section_count": len(latest_entry.get("sections", [])),
                            "node_count": len(latest_entry.get("nodes", [])),
                        }
                    )
                elif hasattr(media_object, "transcripts") and media_object.transcripts:
                    latest_entry = media_object.transcripts[-1]
                    new_frontmatter.update(
                        {
                            "transcript": latest_entry["id"],
                            "node_count": len(latest_entry.get("nodes", [])),
                        }
                    )

                try:
                    new_body = media_object.get_markdown_str()
                except NotImplementedError:
                    new_body = ""

                new_content = f"---\n{yaml.dump(new_frontmatter)}---\n{new_body}"
                with open(pointer_path, "w") as file:
                    file.write(new_content)

        elif "tag" in metadata:
            tag_id = metadata["tag"]
            tag = next((tag for tag in self.tags if tag["id"] == tag_id), None)
            if tag:
                new_content = f"---\ntitle: {tag['name']}\nid: {tag_id}\n---\n{tag.get('description', '')}"
                with open(pointer_path, "w") as file:
                    file.write(new_content)

        elif "group" in metadata:
            group_id = metadata["group"]
            group = next((group for group in self.groups if group.id == group_id), None)
            if group:
                new_content = self.create_group_pointer(
                    group, os.path.dirname(pointer_path)
                )
                with open(pointer_path, "w") as file:
                    file.write(new_content)

    def sync_pointers(self, target_dir):
        def read_pointers(target_dir):
            pointers = {}
            for root, _, files in os.walk(target_dir):
                for file in files:
                    if file.endswith(".md"):
                        path = os.path.join(root, file)
                        with open(path, "r") as f:
                            content = f.read()
                            try:
                                frontmatter, _ = content.split("---", 2)[1:]
                                metadata = yaml.safe_load(frontmatter)
                                id_key = (
                                    metadata.get("obj")
                                    or metadata.get("tag")
                                    or metadata.get("group")
                                )
                                if id_key:
                                    pointers[id_key] = path
                            except Exception as e:
                                print(f"Error reading pointer {path}: {e}")
            return pointers

        def compare_state(library, pointers):
            library_state = {}
            for obj in library.media_objects:
                library_state[obj.id] = "object"
            for tag in library.tags:
                library_state[tag["id"]] = "tag"
            for group in library.groups:
                library_state[group.id] = "group"

            missing = {
                id: typ for id, typ in library_state.items() if id not in pointers
            }
            outdated = {id: pointers[id] for id in pointers if id in library_state}
            extra = {
                id: path for id, path in pointers.items() if id not in library_state
            }

            return missing, outdated, extra

        def update_target_dir(library, target_dir, missing, outdated, extra):
            for id, typ in missing.items():
                if typ == "object":
                    obj = next(obj for obj in library.media_objects if obj.id == id)
                    obj_dir = os.path.join(
                        target_dir, f"media/{obj.__class__.__name__.lower()}"
                    )
                    library.create_pointer(obj, dest_path=obj_dir)
                elif typ == "tag":
                    library.create_pointer(id, dest_path=target_dir, mode="quartz")
                elif typ == "group":
                    group = next(group for group in library.groups if group.id == id)
                    group_dir = os.path.join(target_dir, "groups")
                    library.create_pointer(group, dest_path=group_dir, mode="quartz")

            for id, path in outdated.items():
                library.update_pointer(path)

            for id, path in extra.items():
                os.remove(path)

        pointers = read_pointers(target_dir)
        missing, outdated, extra = compare_state(self, pointers)
        update_target_dir(self, target_dir, missing, outdated, extra)

    def get_tag_name(self, tag_id, mode="full"):
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

        if mode == "full":
            return "/".join(parts)
        elif mode == "name":
            return parts[-1]

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

        # unassign from objects
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

        # unassign from groups
        for group in self.groups:
            if tag_id in group.tags:
                print(f"Unassigning from group {group.id[:6]}")
                group.tags.remove(tag_id)

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

    def create_tag(self, name, parent=None, description=""):
        if any(tag["name"].lower() == name.lower() for tag in self.tags):
            raise ValueError(f"Tag '{name}' already exists.")
        tag_id = str(uuid.uuid4())
        tag = {
            "id": tag_id,
            "name": name,
            "parents": [parent] if parent else [],
            "description": description,
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
        potential_matches = [
            tag for tag in self.tags if tag["name"].lower() == target.lower()
        ]

        if len(potential_matches) == 1:
            return potential_matches[0]["id"]
        elif len(potential_matches) > 1:
            conflict_details = "\n".join(
                [f"{match['name']} (ID: {match['id']})" for match in potential_matches]
            )
            raise ValueError(
                f"Multiple matches found for tag '{target}':\n{conflict_details}"
            )
        else:
            raise ValueError(f"No close match found for tag: {target}")

    def query_tag(self, tag_identifier):
        # find by ID or name
        tag = next(
            (tag for tag in self.tags if tag["id"].startswith(tag_identifier)), None
        )
        if not tag:
            # check if identifier is a name
            potential_matches = [
                tag
                for tag in self.tags
                if tag["name"].lower() == tag_identifier.lower()
            ]
            if len(potential_matches) == 1:
                tag = potential_matches[0]
            elif len(potential_matches) > 1:
                conflict_details = "\n".join(
                    [
                        f"{match['name']} (ID: {match['id']})"
                        for match in potential_matches
                    ]
                )
                raise ValueError(
                    f"Multiple matches found for tag '{tag_identifier}':\n{conflict_details}"
                )
            else:
                raise ValueError(f"No tag found with identifier: {tag_identifier}")

        output = [
            f"id: {tag['id']}",
            f"name: {tag['name']}",
        ]

        if tag.get("description"):
            output.append(f"description: {tag['description'][:40]}")

        if tag.get("parents"):
            parent_names = [
                f"{self.get_tag_name(parent)} ({parent[:6]})"
                for parent in tag["parents"]
            ]
            output.append(f"parents: {', '.join(parent_names)}")

        tagged_objects = []
        tagged_transcripts = []
        tagged_speech_data = []

        for obj in self.media_objects:
            if any(t["id"] == tag["id"] for t in obj.metadata.get("tags", [])):
                tagged_objects.append(obj)
            for entry in getattr(obj, "transcripts", []):
                if any(t["id"] == tag["id"] for t in entry.get("tags", [])):
                    tagged_transcripts.append((obj, entry))
            for entry in getattr(obj, "speech_data", []):
                if any(t["id"] == tag["id"] for t in entry.get("tags", [])):
                    tagged_speech_data.append((obj, entry))

        if tagged_objects:
            obj_details = []
            for obj in tagged_objects:
                name = obj.metadata.get("name") or obj.metadata.get(
                    "source_filename", "Unnamed"
                )
                obj_details.append(f"{obj.id[:6]} ({name})")
            output.append(f"objects: {', '.join(obj_details)}")

        if tagged_transcripts:
            entry_details = []
            for obj, entry in tagged_transcripts:
                entry_details.append(f"{entry['id'][:6]}")
            output.append(f"transcripts: {', '.join(entry_details)}")

        if tagged_speech_data:
            entry_details = []
            for obj, entry in tagged_speech_data:
                entry_details.append(f"{entry['id'][:6]}")
            output.append(f"speech_data: {', '.join(entry_details)}")

        tagged_groups = [group for group in self.groups if tag["id"] in group.tags]
        if tagged_groups:
            group_details = [
                f"{group.name if group.name else 'untitled'} ({group.id[:6]})"
                for group in tagged_groups
            ]
            output.append(f"groups: {', '.join(group_details)}")

        return "\n".join(output)

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

    def tag_group(self, group, tag_str):
        tag_id = self.get_tag_id(tag_str)
        if tag_id not in group.tags:
            group.tags.append(tag_id)

    def untag_group(self, group, tag_str):
        tag_id = self.get_tag_id(tag_str)
        if tag_id in group.tags:
            group.tags.remove(tag_id)

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

    def serialize_group(self, group):
        return {
            "id": group.id,
            "name": group.name,
            "created_by": group.created_by,
            "date_created": group.date_created,
            "objects": [obj.id for obj in group.objects],
            "tags": group.tags,
            "groups": [self.serialize_group(subgroup) for subgroup in group.groups],
            "description": group.description,
        }

    def deserialize_group(self, group_data):
        group = Group(
            id=group_data["id"],
            name=group_data["name"],
            created_by=group_data["created_by"],
            description=group_data.get("description", ""),
        )
        group.date_created = group_data["date_created"]
        group.objects = self.fetch(group_data["objects"])
        group.tags = group_data.get("tags", [])
        group.groups = [
            self.deserialize_group(subgroup_data)
            for subgroup_data in group_data.get("groups", [])
        ]
        return group


class Group:
    def __init__(self, id=None, name="", created_by="user", description=""):
        self.id = id if id else str(uuid.uuid4())
        self.name = name
        self.created_by = created_by
        self.date_created = datetime.now().isoformat()
        self.objects = []
        self.groups = []
        self.tags = []
        self.description = description

    def add_objects(self, objects):
        new_objects = [obj for obj in objects if obj not in self.objects]
        if new_objects:
            self.objects.extend(new_objects)
            self.objects.sort(
                key=lambda x: (
                    x.metadata.get("date_recorded"),
                    x.metadata.get("date_stored"),
                )
            )
        else:
            print("No new objects to add.")

    def add_groups(self, groups):
        self.groups.extend(groups)
        self.groups.sort(key=lambda x: x.date_created)

    def get_str(self, merged=False):
        if merged:
            return "\n".join([obj.get_markdown_str() for obj in self.objects])
        return "\n".join([obj.metadata.get("name", obj.id) for obj in self.objects])
