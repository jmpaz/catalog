def read_secrets(filename="secrets.txt"):
    secrets = {}
    with open(filename, "r") as file:
        for line in file:
            key, value = line.strip().split("=", 1)
            secrets[key] = value
    return secrets


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


def query_subtarget(media_object, subtarget):
    parts = subtarget.split(":", 2)
    entry_type = parts[0]
    entry_id = parts[1] if len(parts) > 1 else None
    param = parts[2] if len(parts) > 2 else None

    if entry_type in ["transcripts", "speech_data", "processed_text"]:
        if entry_id:
            entry = fetch_subtarget_entry(media_object, entry_type, entry_id)
            if param:
                return entry.get(param)
            elif entry_type == "speech_data":
                return format_speech_data([entry])
            elif entry_type == "transcripts":
                return format_transcript_nodes([entry])
            else:
                return entry
        else:
            entries = getattr(media_object, entry_type, [])
            if entry_type == "speech_data":
                return format_speech_data(entries)
            elif entry_type == "transcripts":
                return format_transcript_nodes(entries)
            else:
                return entries
    else:
        return None
