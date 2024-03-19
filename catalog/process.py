import whisperx
import torch
import gc
from catalog.utils import read_secrets


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
        ]
    }

    # Store in the audio object's transcripts list
    audio_obj.transcripts.append(transcription)

    # Clean up memory
    gc.collect()
    torch.cuda.empty_cache()
    del model_a
