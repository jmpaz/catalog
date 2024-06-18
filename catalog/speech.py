import uuid
from datetime import datetime

from sexpdata import loads


def resegment_transcript(transcription: dict, processor_params=None):
    """Parse a transcript's contents into logical segments."""

    def _prepare_segments(nodes, numbering=False):
        """Prepare a string from `nodes` for further processing (if needed)."""
        if numbering:
            segments = [f"{i+1}|{node['content']}" for i, node in enumerate(nodes)]
        else:
            segments = [node["content"] for node in nodes]
        print(f"{len(segments)} nodes processed.")
        return "\n".join(segments)

    # prepare segments
    nodes = transcription["nodes"]
    segments = _prepare_segments(nodes)

    def _call_simulator(segments, processor_params):
        """Call the simulator to resegment the transcript."""
        import tempfile

        from simulators.sims import run_sim

        input_file = tempfile.NamedTemporaryFile()
        input_paths = [input_file.name]
        example_paths = processor_params.get("example_paths", [])

        # write the prepared segments to a tempfile
        with open(input_paths[0], "w") as file:
            file.write(segments)

        # run the simulator
        result = run_sim(
            sim_path=processor_params.get("sim_path", "sim.yaml"),
            sim_path_r2=processor_params.get("sim_path_r2", "sim.yaml"),
            input_paths=input_paths,
            example_paths=example_paths,
            inference_fn=processor_params.get("inference_fn", None),
            model=processor_params.get("model", "claude-sonnet"),
            temperature=processor_params.get("temperature", 0.4),
            max_tokens=processor_params.get("max_tokens", 4096),
            debug=processor_params.get("debug", False),
        )

        return result["cleaned"]

    return _call_simulator(segments, processor_params)


def parse_sexp(sexp_string):
    sexp = loads(sexp_string)
    sections = []
    nodes = []

    def process_node(node, parent_index=None):
        if isinstance(node, list):
            node_index = len(nodes)
            nodes.append({"index": node_index, "text": node[0], "parent": parent_index})
            for subnode in node[1:]:
                process_node(subnode, node_index)
        else:
            node_index = len(nodes)
            nodes.append({"index": node_index, "text": node, "parent": parent_index})

    for section in sexp[1:]:
        label = section[1]
        start_index = len(nodes)
        for node in section[2:]:
            process_node(node)
        end_index = len(nodes) - 1
        sections.append({"label": label, "indeces": (start_index, end_index)})

    return {"sections": sections, "nodes": nodes}


def prepare_speech_data(mediaobject, target=None, sim_params=None):
    if target is None:
        transcript = mediaobject.transcripts[-1]
    elif isinstance(target, int):
        transcript = mediaobject.transcripts[target]
    else:
        transcript = next(t for t in mediaobject.transcripts if t["id"] == target)

    speech_data = {
        "id": str(uuid.uuid4()),
        "date_stored": datetime.now().isoformat(),
        "source_transcript": transcript["id"],
    }

    if sim_params:
        speech_data["process_mode"] = "simulator"
        speech_data["processor_params"] = sim_params

        sexp_result = resegment_transcript(transcript, sim_params)
        parsed_data = parse_sexp(sexp_result)
        speech_data["sections"] = parsed_data["sections"]
        speech_data["nodes"] = parsed_data["nodes"]
    else:
        raise NotImplementedError("`sim_params` are currently required")

    return speech_data
