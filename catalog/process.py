import whisperx
import torch
import gc


def transcribe(audio_obj, device="cuda", batch_size=16, compute_type="float16"):
    if not hasattr(audio_obj, "can_transcribe"):
        raise ValueError("This media object cannot be transcribed")

    print("Preparing to transcribe")
    model = whisperx.load_model("large-v2", device=device, compute_type=compute_type)
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

    # Create a transcription object containing segment nodes
    transcription = {
        "nodes": [
            {
                "content": segment["text"],
                "start": segment["start"],
                "end": segment["end"],
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
