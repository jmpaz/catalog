import json
import os
from datetime import datetime


class Logger:
    def __init__(self, log_file):
        self.log_file = log_file
        self.log_data = self._read_existing_log() or {"sessions": []}

    def _read_existing_log(self):
        if os.path.exists(self.log_file):
            with open(self.log_file, "r") as file:
                return json.load(file)
        return None

    def info(self, message):
        # Add an info log to the current session
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "level": "INFO",
            "message": message,
        }
        self.current_session.setdefault("logs", []).append(log_entry)
        print(f"INFO: {message}")  # Optional: print to console

    def error(self, message):
        # Add an error log to the current session
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "level": "ERROR",
            "message": message,
        }
        self.current_session.setdefault("logs", []).append(log_entry)
        print(f"ERROR: {message}")  # Optional: print to console

    def start_session(self, args):
        self.current_session = {
            "start_time": datetime.now().isoformat(),
            "arguments": {k: str(v) for k, v in vars(args).items() if k != "func"},
            "files_processed": [],
        }

    def log_file_process(self, file_path, start_time, end_time):
        self.current_session["files_processed"].append(
            {
                "file": file_path,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration": str(end_time - start_time),
            }
        )

    def end_session(self):
        self.current_session["end_time"] = datetime.now().isoformat()
        self.current_session["session_duration"] = str(
            datetime.now() - datetime.fromisoformat(self.current_session["start_time"])
        )
        self.log_data["sessions"].append(self.current_session)

    def save_log(self):
        with open(self.log_file, "w") as file:
            json.dump(self.log_data, file, indent=4)
