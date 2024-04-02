import whisperx
import torch
import gc
from catalog.utils import read_secrets
import re


def transcribe(
    audio_obj,
    device="cuda",
    batch_size=16,
    compute_type="float16",
    diarize=False,
    speaker_count=1,
    initial_prompt=None,
):
    if not hasattr(audio_obj, "can_transcribe"):
        raise ValueError("This media object cannot be transcribed")

    print("Preparing to transcribe")
    model = whisperx.load_model(
        "large-v2",
        device=device,
        compute_type=compute_type,
        asr_options={"initial_prompt": initial_prompt},
    )
    audio = whisperx.load_audio(audio_obj.file_path)
    result = model.transcribe(audio, batch_size=batch_size)
    print(f"Results (before alignment): {result['segments']}")

    # Align whisper output
    model_a, metadata = whisperx.load_align_model(
        language_code=result["language"], device=device
    )
    result = whisperx.align(
        result["segments"],
        model_a,
        metadata,
        audio,
        device,
        return_char_alignments=False,
    )
    print(f"Results (after alignment): {result['segments']}")

    if diarize:
        hf_token = read_secrets()["HF_TOKEN"]
        diarize_model = whisperx.DiarizationPipeline(
            use_auth_token=hf_token, device=device
        )

        if speaker_count > 1:
            diarize_segments = diarize_model(
                audio, min_speakers=speaker_count, max_speakers=speaker_count
            )
        else:
            diarize_segments = diarize_model(audio)

        result = whisperx.assign_word_speakers(diarize_segments, result)
        print(diarize_segments)
        print(f"Results (after diarization): {result['segments']}")

    # Create a transcription object containing segment nodes
    transcription = {
        "nodes": [
            {
                "start": segment["start"],
                "end": segment["end"],
                "speaker": segment["speaker"] if diarize else None,
                "content": segment["text"],
                "words": segment["words"],
            }
            for segment in result["segments"]
        ],
        # TODO: store used params
    }

    # Store in the audio object's transcripts list
    audio_obj.transcripts.append(transcription)

    # Clean up memory
    gc.collect()
    torch.cuda.empty_cache()
    del model_a


def format_transcript(
    transcription: dict,
    sensitivity=0.5,
    include_timestamps=True,
    timestamp_interval=120,
    timestamp_every_n_chunks=None,
):
    for segment in transcript_data["nodes"]:
        segment["content"] = re.sub(
            r"^\s+", "", re.sub(r"\s+$", "", segment["content"])
        )

    chunks = [segment["content"] for segment in transcript_data["nodes"]]
    start_times = [segment["start"] for segment in transcript_data["nodes"]]
    end_times = [segment["end"] for segment in transcript_data["nodes"]]

    pauses = [start_times[i] - end_times[i - 1] for i in range(1, len(start_times))]
    min_pause = min(pauses)
    max_pause = max(pauses)
    threshold = min_pause + (max_pause - min_pause) * sensitivity

    result = "**00:00**\n\n"
    last_timestamp = 0
    chunk_counter = 0
    total_duration = end_times[-1]

    for i in range(len(chunks)):
        if include_timestamps:
            current_time = start_times[i]
            if (current_time - last_timestamp >= timestamp_interval) or (
                timestamp_every_n_chunks
                and chunk_counter % timestamp_every_n_chunks == 0
            ):
                if not result.endswith("\n\n"):
                    result += "\n\n"
                if total_duration >= 3600:
                    timestamp = f"\n**{int(current_time // 3600):02d}:{int((current_time % 3600) // 60):02d}:{int(current_time % 60):02d}**\n\n"
                else:
                    timestamp = f"\n**{int(current_time // 60):02d}:{int(current_time % 60):02d}**\n\n"
                result += timestamp
                last_timestamp = current_time

        result += chunks[i]
        chunk_counter += 1

        if i < len(chunks) - 1:
            pause = start_times[i + 1] - end_times[i]
            if pause < threshold:
                result += " "
            else:
                result += "\n\n"

    return result
