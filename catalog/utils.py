def read_secrets(filename="secrets.txt"):
    secrets = {}
    with open(filename, "r") as file:
        for line in file:
            key, value = line.strip().split("=", 1)
            secrets[key] = value
    return secrets


def clear_memory():
    import gc
    import torch

    gc.collect()
    torch.cuda.empty_cache()


def extract_metadata(file_path):
    import json
    import shlex
    import subprocess

    def run_ffprobe(file_path):
        cmd = "ffprobe -v quiet -print_format json -show_format -show_streams '{}'".format(
            file_path
        )
        args = shlex.split(cmd)
        result = subprocess.run(
            args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        return result.stdout

    metadata = json.loads(run_ffprobe(file_path))
    creation_time = (
        metadata.get("streams", [{}])[0].get("tags", {}).get("creation_time", None)
    )
    duration = metadata.get("format", {}).get("duration", None)

    return {"creation_time": creation_time, "duration": duration}


def detect_depth(text):
    """Assess indentation depth of a string to determine if it should be flattened."""
    lines = text.split("\n")
    indent_sizes = []
    current_indent = None
    deepest_indent = 0
    unclosed_nests = 0

    for line in lines:
        stripped_line = line.lstrip()
        if not stripped_line or stripped_line.startswith("#"):
            continue  # Skip empty lines and headings
        indent_size = len(line) - len(stripped_line)
        if current_indent is None:
            current_indent = indent_size
        if indent_size > deepest_indent:
            deepest_indent = indent_size
        if indent_size > current_indent:
            unclosed_nests += 1
        else:
            unclosed_nests -= 1 if unclosed_nests > 0 else 0
        indent_sizes.append(indent_size)
        current_indent = indent_size

    return unclosed_nests > (len(indent_sizes) - unclosed_nests)


def flatten_markdown(text):
    lines = text.split("\n")
    flattened_lines = []
    within_chunk = False

    for line in lines:
        stripped_line = line.lstrip()
        if not stripped_line or stripped_line.startswith("#"):
            flattened_lines.append(line)  # Keep headings and empty lines as is
            continue
        if detect_depth("\n".join(lines[lines.index(line) :])):
            within_chunk = True
        if within_chunk:
            flattened_lines.append(stripped_line)
        else:
            flattened_lines.append(line)
    return "\n".join(flattened_lines)


def format_speech_data(speech_data, minimal=False):
    def _calculate_depth(nodes, index):
        depth = 0
        current_index = index
        while current_index is not None:
            current_node = next(
                (node for node in nodes if node["index"] == current_index), None
            )
            if current_node:
                current_index = current_node.get("parent")
                depth += 1
            else:
                current_index = None
        return depth - 1

    output = []
    for entry in speech_data:
        for key, value in entry.items():
            if key == "nodes":
                continue
            if key == "processor_params" and not minimal:
                output.append("parameters:")
                for param_key, param_value in value.items():
                    output.append(f"  {param_key}: {param_value}")
                output.append("\n------------")
            elif key == "sections":
                for section in value:
                    output.append(f"\n## {section['label']}")
                    for index in range(
                        section["indeces"][0], section["indeces"][1] + 1
                    ):
                        message = next(
                            (node for node in entry["nodes"] if node["index"] == index),
                            None,
                        )
                        if message:
                            depth = _calculate_depth(entry["nodes"], index)
                            indent = "  " * depth
                            output.append(f"{indent}- {message['text']}")
                    output.append("")
                if not minimal:
                    output.append("\n============\n")
            elif not minimal:
                output.append(f"{key.replace('_', ' ')}: {value}")
        output.append("")
    return "\n".join(output).strip()


def format_transcript_nodes(transcripts, minimal=False):
    output = []
    for transcript in transcripts:
        for key, value in transcript.items():
            if key == "params" and not minimal:
                output.append("Params:")
                for param_key, param_value in value.items():
                    output.append(f"  {param_key}: {param_value}")
            elif key == "nodes":
                if not minimal:
                    output.append(f"nodes: {len(value)}")
                    output.append("\n------------\n")
                for node in value:
                    output.append(node["content"])
                    output.append("")
                if not minimal:
                    output.append("============\n")
            elif not minimal:
                output.append(f"{key.replace('_', ' ')}: {value}")
    return "\n".join(output)


def fetch_subtarget_entry(media_object, entry_type, entry_id):
    """Fetch a specific entry from a media object by index, partial/full UUID, or -1 for the last entry."""
    entries = getattr(media_object, entry_type, [])

    try:
        # fetch by index, or -1 for the last entry
        index = int(entry_id)
        if index == -1:
            return entries[-1] if entries else None
        elif 0 <= index < len(entries):
            return entries[index]
        else:
            raise ValueError(f"Index out of range: {entry_id}")
    except ValueError:
        # fetch by UUID
        entry = next((e for e in entries if e["id"].startswith(entry_id)), None)
        if entry:
            return entry
        else:
            raise ValueError(f"No {entry_type} entry found with ID: {entry_id}")


def get_available_subtargets(media_object):
    from catalog.media import MediaObject

    if not isinstance(media_object, MediaObject):
        raise ValueError("Invalid media object")

    subtargets = []
    for attr in dir(media_object):
        if not attr.startswith("_") and not callable(getattr(media_object, attr)):
            value = getattr(media_object, attr)
            if value:
                subtargets.append(attr)
    for key, value in media_object.metadata.items():
        if value:
            subtargets.append(key)
    return subtargets


def update_node_content(locator, new_content, author="user"):
    """Update the content of a node within a media object entry."""
    import os
    from datetime import datetime
    from catalog.library import Library

    def parse_node_locator(locator):
        parts = locator.split(":")
        if len(parts) < 3:
            raise ValueError(
                "Invalid locator format. Expected format: 'media_id:entry_type:entry_id.nodes:node_index'"
            )

        media_id = parts[0]
        entry_type = parts[1]
        entry_id_part = parts[2]
        subfield = None
        subfield_range = None

        if "." in entry_id_part:
            entry_parts = entry_id_part.split(".")
            entry_id = entry_parts[0]
            subfield = entry_parts[1]
            if len(entry_parts) > 2:
                subfield_range = entry_parts[2]

        if subfield and subfield_range is None and ":" in locator:
            subfield_range = locator.split(":")[-1]

        if subfield != "nodes":
            raise ValueError("Invalid subfield type. Expected 'nodes'.")

        node_index = int(subfield_range) if subfield_range else None

        return media_id, entry_type, entry_id, node_index

    def fetch_node(library, media_id, entry_type, entry_id, node_index):
        media_object = library.fetch([media_id])[0]
        entry = fetch_subtarget_entry(media_object, entry_type, entry_id)
        if "nodes" not in entry:
            raise ValueError("Entry does not contain nodes.")
        if node_index < 0 or node_index >= len(entry["nodes"]):
            raise IndexError("Node index out of range.")
        return media_object, entry, entry["nodes"][node_index]

    library_path = os.path.expanduser("~/.config/catalog/library.json")
    library = Library(library_path)

    media_id, entry_type, entry_id, node_index = parse_node_locator(locator)
    media_object, entry, node = fetch_node(
        library, media_id, entry_type, entry_id, node_index
    )

    if "value_history" not in node:  # initialize
        node["value_history"] = [
            {
                "version": 1,
                "content": node.get("content") or node.get("text"),
                "updated_at": node.get("updated_at"),
                "updated_by": node.get("updated_by"),
            }
        ]
        current_version = 1
    else:
        current_version = len(node["value_history"])

    history_entry = {
        "version": current_version + 1,
        "content": new_content,
        "updated_at": datetime.now().isoformat(),
        "updated_by": author,
    }

    if "content" in node:
        node["content"] = new_content
    elif "text" in node:
        node["text"] = new_content
    else:
        raise ValueError("Node does not have 'content' or 'text' field.")

    node["value_history"].append(history_entry)
    library.save_library()
