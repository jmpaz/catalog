def read_secrets(filename="secrets.txt"):
    secrets = {}
    with open(filename, "r") as file:
        for line in file:
            key, value = line.strip().split("=", 1)
            secrets[key] = value
    return secrets


def _format_speech_data(speech_data):
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
            if key == "processor_params":
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
                output.append("\n============\n")
            else:
                output.append(f"{key.replace('_', ' ')}: {value}")
        output.append("")
    return "\n".join(output)


def _format_transcript_nodes(transcripts):
    output = []
    for transcript in transcripts:
        for key, value in transcript.items():
            if key == "params":
                output.append("Params:")
                for param_key, param_value in value.items():
                    output.append(f"  {param_key}: {param_value}")
            elif key == "nodes":
                output.append(f"nodes: {len(value)}")
                output.append("\n------------\n")
                for node in value:
                    output.append(node["content"])
                    output.append("")
                output.append("============\n")
            else:
                output.append(f"{key.replace('_', ' ')}: {value}")
    return "\n".join(output)
