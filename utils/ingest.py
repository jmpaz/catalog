import os
import sys
import re
import json
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from pytz import timezone


class FileExtractor:
    """
    Base class for file extractors.

    Attributes:
        source_dir (str): Directory containing audio files to process.
        target_dir (str): Directory where processed files will be stored.

    Usage:
        # Initialize the extractor with source and target directories
        extractor = Extractor('/path/to/source', '/path/to/target')

        # Process files
        extractor.process_directory()
    """

    def __init__(self, source_dir, target_dir):
        self.source_dir = source_dir
        self.target_dir = target_dir

    def process_directory(self):
        """
        Processes all files in the source directory.
        Subclasses should implement specific processing logic.
        """
        raise NotImplementedError("Must be implemented in subclasses.")

    def move_file(self, file_path, new_path):
        os.makedirs(os.path.dirname(new_path), exist_ok=True)
        os.rename(file_path, new_path)


class PixelExtractor(FileExtractor):
    """
    Extractor subclass for handling audio files created by Google Pixel phones' Recorder app.

    Pulls audio files from a source directory and processes them, deriving a start time based on
    `creation_time` (UTC) and `duration` values from file metadata before moving them to a target directory.

    Inherited Attributes:
        source_dir (str): Directory containing audio files to process.
        target_dir (str): Directory where processed files will be stored.

    Additional Attributes:
        location (str): Used for DST calculations. Defaults to 'America/New_York'.
        utc_offset (int): The UTC offset for the location. Defaults to -5 for 'America/New_York'.

    Usage:
        # Initialize the extractor with source and target directories
        extractor = PixelExtractor('/path/to/source', '/path/to/target')

        # Process files
        extractor.process_directory()
    """

    def __init__(
        self, source_dir, target_dir, location="America/New_York", utc_offset=-5
    ):
        super().__init__(source_dir, target_dir)
        self.location = location
        self.utc_offset = utc_offset

    def process_directory(self):
        file_paths = [
            os.path.join(self.source_dir, filename)
            for filename in os.listdir(self.source_dir)
        ]
        results = self.process_files(file_paths)
        for filename, date_obj, time_str in results:
            date_str = date_obj.strftime("%Y-%m-%d")
            year_month = date_str[
                :7
            ]  # Extract YYYY-MM part for the directory structure
            source_file = os.path.join(self.source_dir, filename)

            # Construct the target path without adding extra zeroes
            target_path = os.path.join(
                self.target_dir, year_month, date_str, f"{time_str}.m4a"
            )
            self.move_file(source_file, target_path)

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

    def estimate(self, creation_time, duration_sec):
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

    def derive_timestamp(self, file_time_str, creation_time, duration_sec, location):
        is_estimate = (
            not file_time_str
        )  # Estimate only if no time extracted from filename
        is_dst = self.get_dst_status(creation_time, location)
        estimated_start_time = self.estimate(creation_time, duration_sec)
        timezone_offset = self.utc_offset + (1 if is_dst else 0)

        # If a time is extracted from the filename, use it
        if file_time_str:
            file_time_full_str = f"{estimated_start_time.date()} {file_time_str}"
            filename_datetime = datetime.strptime(
                file_time_full_str, "%Y-%m-%d %I:%M %p"
            )
            time_difference = filename_datetime - estimated_start_time
            time_difference_in_hours = time_difference / timedelta(hours=1)
            timezone_offset = round(time_difference_in_hours)
            adjusted_time = filename_datetime
        else:
            adjusted_time = estimated_start_time + timedelta(hours=timezone_offset)

        return adjusted_time.date(), adjusted_time.strftime("%H-%M-%S"), is_estimate

    def process_files(self, file_paths):
        location = self.location
        results = []
        for file_path in file_paths:
            filename = Path(file_path).name
            creation_time, duration = self.get_metadata(file_path)
            if creation_time and duration:
                file_time_str = self.extract_time_from_filename(filename)
                date_str, time_str, is_estimate = self.derive_timestamp(
                    file_time_str, creation_time, duration, location
                )
                results.append((filename, date_str, time_str))
                if is_estimate:
                    print(
                        f"{date_str} {time_str} (UTC{self.utc_offset:+d}) estimated for {file_path}"
                    )
                else:
                    print(f"Copied {file_path} to {date_str}/{time_str}.m4a")
        return results

    def get_metadata(self, file_path):
        file_path = (
            os.path.expanduser(file_path) if file_path.startswith("~") else file_path
        )

        try:
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
