from datetime import datetime, timedelta
from transcribe.transcribe import accumulate_time
import pysrt


def hf_pipeline_to_srt(json_result, output_file=None):
    # Accumulate time for each chunk
    accumulated_chunks = accumulate_time(json_result["chunks"])

    file = pysrt.SubRipFile()
    for idx, chk in enumerate(accumulated_chunks):
        text = chk["text"]
        start, end = map(convert_time, chk["timestamp"])

        sub = pysrt.SubRipItem(idx, start=start, end=end, text=text.strip())
        file.append(sub)

    if output_file is not None:
        file.save(output_file)
        return output_file
    else:
        import io

        fp = io.StringIO("")
        file.write_into(fp)
        json_result = fp.getvalue()
        return json_result


def convert_time(data):
    total_seconds = int(data)
    milliseconds = int((data - total_seconds) * 1000)

    time_delta = timedelta(seconds=total_seconds, milliseconds=milliseconds)
    base_time = datetime(2000, 1, 1)

    result_time = base_time + time_delta
    result_str = result_time.strftime("%H:%M:%S,%f")[:-3]

    return result_str


def hf_pipeline_to_lrc(json_result, output_file=None):
    accumulated_chunks = accumulate_time(json_result["chunks"])

    lrc_lines = []

    for idx, chunk in enumerate(accumulated_chunks):
        # Extract start and end times for each chunk
        start_time, end_time = chunk["timestamp"]

        # Convert start time to LRC format
        lrc_line = f"[{convert_time_to_lrc_format(start_time)}] {chunk['text']}"
        lrc_lines.append(lrc_line)

    lrc_content = "\n".join(lrc_lines)

    if output_file:
        with open(output_file, "w") as file:
            file.write(lrc_content)
    else:
        return lrc_content


def convert_time_to_lrc_format(time_data):
    # Convert to minutes and seconds format
    minutes = int(time_data / 60)
    seconds = int(time_data % 60)
    time_str = f"{minutes:02}:{seconds:02}.0"
    return time_str
