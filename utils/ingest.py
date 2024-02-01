import os
import sys
import re
import json
import subprocess

from pathlib import Path
from pytz import timezone
from datetime import datetime, timedelta


class PixelExtractor:
    """
    Retrieves the start time for audio files created by Pixel Recorder using `creation_time` (UTC) and `duration` values from file metadata.


    Attributes:
        file_paths (list): A list of file paths for the audio files to process.
        default_utc_offset (int): An optional UTC offset (default is -5). This is used when a filename time is not available.

    Methods:
        process_files(location): Processes the list of audio files, extracting or estimating timestamps.
            - location (str): A string representing the location (e.g., 'America/New_York') used for DST calculations.

    Usage:
        # Initialize the extractor with a list of file paths
        extractor = PixelExtractor([
            "/path/to/file1.m4a",
            "/path/to/file2.m4a",
            ...
        ])

        # Process the files with a specified location for DST adjustment
        results = extractor.process_files('America/New_York')

        # results will be a list of tuples containing estimated dates and times:
        # [('file1', 'YYYY-MM-DD', 'HH-MM'), ('file2', 'YYYY-MM-DD', 'HH-MM'), ...]

    """

    def __init__(self, file_paths, default_utc_offset=-5):
        self.file_paths = file_paths
        self.default_utc_offset = default_utc_offset

    def extract_time_from_filename(self, filename):
        time_pattern = r"(\d{1,2})[ _-](\d{1,2}) ?(AM|PM)|(\d{1,2})_(\d{1,2})(am|pm)"
        match = re.search(time_pattern, filename, re.IGNORECASE)
        if match:
            if match.group(3):  # HH-MM format
                hours, minutes, am_pm = match.groups()[:3]
            else:  # HHpm format
                hours, minutes, am_pm = match.groups()[3:]
            am_pm = am_pm.upper()
            return f"{int(hours):02d}:{int(minutes):02d} {am_pm}"
        return None

    def timestamp_estimate(self, creation_time, duration_sec):
        creation_datetime = datetime.strptime(creation_time, "%Y-%m-%dT%H:%M:%S.%fZ")
        estimated_start_time = creation_datetime - timedelta(seconds=duration_sec)
        return estimated_start_time

    def get_dst_status(self, creation_time, location):
        creation_datetime = datetime.strptime(creation_time, "%Y-%m-%dT%H:%M:%S.%fZ")
        local_tz = timezone(location)
        # Convert creation_datetime to a naive datetime object before localizing
        creation_datetime_naive = creation_datetime.replace(tzinfo=None)
        # Localize the datetime object to the specified timezone
        creation_datetime_local = local_tz.localize(
            creation_datetime_naive, is_dst=None
        )
        # Return DST status
        return creation_datetime_local.dst() != timedelta(0)

    def guess_timezone(self, file_time_str, creation_time, duration_sec, location):
        is_dst = self.get_dst_status(creation_time, location)
        estimated_start_time = self.timestamp_estimate(creation_time, duration_sec)
        timezone_offset = self.default_utc_offset + (1 if is_dst else 0)

        if file_time_str:
            file_time_full_str = f"{estimated_start_time.date()} {file_time_str}"
            filename_datetime = datetime.strptime(
                file_time_full_str, "%Y-%m-%d %I:%M %p"
            )
            time_difference = filename_datetime - estimated_start_time
            time_difference_in_hours = time_difference / timedelta(hours=1)
            timezone_offset = round(time_difference_in_hours)

        adjusted_time = estimated_start_time + timedelta(hours=timezone_offset)
        return adjusted_time.date(), adjusted_time.strftime("%H-%M")

    def process_files(self, location):
        results = []
        for file_path in self.file_paths:
            filename = Path(file_path).stem
            creation_time, duration = self.get_metadata(file_path)
            file_time_str = self.extract_time_from_filename(filename)
            date_str, time_str = self.guess_timezone(
                file_time_str, creation_time, duration, location
            )
            results.append((filename, date_str, time_str))
        return results

    def get_metadata(self, file_path):
        # Expand the '~' to the user's home directory
        file_path = os.path.expanduser(file_path)

        try:
            # Running the ffprobe command
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-print_format",
                    "json",
                    "-show_streams",
                    file_path,
                ],
                capture_output=True,
                text=True,
            )

            # Log the ffprobe output for debugging
            # print("ffprobe output:", result.stdout, file=sys.stderr)
            # print("ffprobe errors:", result.stderr, file=sys.stderr)

            metadata = json.loads(result.stdout)

            # Extract creation_time and duration from the metadata
            creation_time = None
            duration = None
            for stream in metadata.get("streams", []):
                tags = stream.get("tags", {})
                if "creation_time" in tags:
                    creation_time = tags["creation_time"]
                if "duration" in stream:
                    duration = float(stream["duration"])

            return creation_time, duration
        except Exception as e:
            print(f"Error processing file {file_path}: {e}", file=sys.stderr)
            return None, None
