import torch
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline

device = "cuda:0"
torch_dtype = torch.float16

model_id = "distil-whisper/distil-large-v2"

model = AutoModelForSpeechSeq2Seq.from_pretrained(
    model_id,
    torch_dtype=torch_dtype,
    low_cpu_mem_usage=True,
    use_safetensors=True,
    # attn_implementation="flash_attention_2",
)
model.to(device)

processor = AutoProcessor.from_pretrained(model_id)

pipe = pipeline(
    "automatic-speech-recognition",
    model=model,
    tokenizer=processor.tokenizer,
    feature_extractor=processor.feature_extractor,
    max_new_tokens=128,
    torch_dtype=torch_dtype,
    device=device,
)


def accumulate_time(chunks):
    accumulated_time = 0
    new_chunks = []

    for chunk in chunks:
        new_start = round(accumulated_time, 3)  # Round to three decimal places
        duration = round(chunk["timestamp"][1] - chunk["timestamp"][0], 3)
        new_end = new_start + duration
        accumulated_time = new_end

        new_chunk = chunk.copy()
        new_chunk["timestamp"] = [new_start, new_end]
        new_chunks.append(new_chunk)

    return new_chunks


def transcribe_audio(file_path):
    result = pipe(file_path, return_timestamps=True)
    result["chunks"] = accumulate_time(result["chunks"])
    return result
