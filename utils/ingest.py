import os
import shutil
import sys
import re
import json
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from pytz import timezone
from utils.file_handling import extract_label


class iCloudExtractor:
    """
    Extractor for retrieving audio files from iCloud Drive.

    Attributes:
        api (ICloudPyService): iCloud service instance for accessing files.
        base_path (str): Path within iCloud Drive to start processing.
        target_dir (str): Directory where processed files will be stored.
        debug (bool): Enables debug mode for dry runs.
    """

    def __init__(self, api, base_path, target_dir, debug=False):
        self.api = api
        self.base_path = base_path
        self.target_dir = target_dir
        self.debug = debug

    def process_source(self):
        self.process_directory(self.api.drive[self.base_path], self.base_path)

    def process_directory(self, drive_node, base_path):
        if hasattr(drive_node, "dir") and drive_node.size is None:
            contents = drive_node.dir()
            if contents is None:
                print(f"Warning: No contents found in '{base_path}'.")
                return
            for item in contents:
                item_node = drive_node[item]
                new_base_path = os.path.join(base_path, item)
                if item_node.size is None:
                    self.process_directory(item_node, new_base_path)
                else:
                    self.process_item(item_node, new_base_path)
        else:
            self.process_item(drive_node, base_path)

    def process_item(self, item_node, base_path):
        filename = os.path.basename(base_path)
        destination_path = self.construct_destination_path(base_path, filename)
        # Check if the download and sync are necessary
        if os.path.exists(destination_path):
            print(f"Skipping {filename}, already up to date.")
        else:
            if self.debug:
                print(
                    f"DEBUG: Would download {filename} and sync to {destination_path}"
                )
            else:
                self.download_and_sync(item_node, destination_path)

    def construct_destination_path(self, base_path, filename):
        # Extract date components from base_path if available
        date_match = re.search(r"(\d{4})-(\d{2})-(\d{2})", base_path)
        if date_match:
            year, month, day = date_match.groups()
            destination_dir = os.path.join(
                self.target_dir, year, f"{year}-{month}", f"{year}-{month}-{day}"
            )
        else:
            destination_dir = os.path.join(self.target_dir, "Undated")

        if not os.path.exists(destination_dir):
            os.makedirs(destination_dir)

        return os.path.join(destination_dir, filename)

    def download_and_sync(self, drive_node, destination_path):
        if self.debug:
            print(
                f"DEBUG: Would download {drive_node.name} to temp file and sync to {destination_path}"
            )
        else:
            with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                self.download_file(drive_node, tmp_file.name)
                self.sync_file(tmp_file.name, destination_path)
                os.remove(tmp_file.name)

    def download_file(self, drive_node, local_path):
        print(f"Downloading {drive_node.name} to {local_path}")
        try:
            with drive_node.open(stream=True) as response, open(
                local_path, "wb"
            ) as file:
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        file.write(chunk)
            print(f"Successfully downloaded: {drive_node.name}")
        except Exception as e:
            print(f"Error downloading file: {e}")

    def sync_file(self, source_path, destination_path):
        print(f"Syncing {source_path} to {destination_path}")
        try:
            subprocess.run(["rsync", "-av", source_path, destination_path], check=True)
            print(f"Successfully synced: {source_path} to {destination_path}")
        except subprocess.CalledProcessError as e:
            print(f"Error syncing file: {e}")


class PixelExtractor:
    """
    Extractor for handling audio files created by Google Pixel phones' Recorder app.

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
        self,
        source_dir,
        target_dir,
        mode="sync",
        location="America/New_York",
        utc_offset=-5,
    ):
        self.source_dir = source_dir
        self.target_dir = target_dir
        self.mode = mode
        self.location = location
        self.utc_offset = utc_offset

    def process_source(self):
        self.process_directory(self.source_dir)

    def process_directory(self, debug=False):
        source_dir = self.source_dir
        mode = self.mode
        summary = {"processed": 0, "skipped": 0}
        file_paths = [
            os.path.join(source_dir, filename) for filename in os.listdir(source_dir)
        ]
        results = self.process_files(file_paths)
        for filename, date_obj, time_str in results:
            date_str = date_obj.strftime("%Y-%m-%d")
            year_month = date_str[:7]  # YYYY-MM
            source_file = os.path.join(source_dir, filename)

            label = extract_label(filename)

            # Construct the target path with the label
            target_filename = f"{time_str} {label}.m4a" if label else f"{time_str}.m4a"
            target_path = os.path.join(
                self.target_dir, year_month, date_str, target_filename
            )
            if debug:
                print(f"\n{filename}\n-> {year_month}/{target_filename}")
            else:
                if mode == "sync":
                    if not os.path.exists(target_path):
                        os.makedirs(os.path.dirname(target_path), exist_ok=True)
                        shutil.copy2(source_file, target_path)
                        print(f"Copied: {source_file} to {target_path}")
                        summary["processed"] += 1
                    else:
                        print(f"Skipped (already exists): {target_path}")
                        summary["skipped"] += 1
                elif mode == "move":
                    self.move_file(source_file, target_path)
        return summary

    def move_file(self, file_path, new_path):
        os.makedirs(os.path.dirname(new_path), exist_ok=True)
        os.rename(file_path, new_path)

    def extract_time(self, filename):
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
                file_time_str = self.extract_time(filename)
                date_str, time_str, is_estimate = self.derive_timestamp(
                    file_time_str, creation_time, duration, location
                )
                results.append((filename, date_str, time_str))
                # if is_estimate:
                #     print(
                #         f"{date_str} {time_str} (UTC{self.utc_offset:+d}) estimated for {file_path}"
                #     )
                # else:
                #     print(f"Resolved {file_path} to {date_str}/{time_str}")
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
