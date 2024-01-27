import json
import os
from datetime import datetime


class Logger:
    def __init__(self, log_file):
        self.log_file = log_file
        self.log_data = self._read_existing_log() or {"sessions": []}
        self.current_session = None

    def _read_existing_log(self):
        if os.path.exists(self.log_file):
            with open(self.log_file, "r") as file:
                return json.load(file)
        return None

    def info(self, message):
        if self.current_session is None:
            print("Logging session not started. Unable to log INFO message.")
            return
        # Add an info log to the current session
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "level": "INFO",
            "message": message,
        }
        self.current_session.setdefault("logs", []).append(log_entry)
        print(f"INFO: {message}")  # Optional: print to console

    def error(self, message):
        if self.current_session is None:
            print("Logging session not started. Unable to log ERROR message.")
            return
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

    def log_file_process(self, synced_files, deleted_files, dest_path):
        # Ensure current_session is not None
        if self.current_session is None:
            print("Logging session not started. Unable to log file operations.")
            return

        # Record synced and deleted files in the current session
        for file in synced_files:
            self.current_session["files_processed"].append(
                {"action": "synced", "file": file, "destination": dest_path}
            )
        for file in deleted_files:
            self.current_session["files_processed"].append(
                {"action": "deleted", "file": file, "destination": dest_path}
            )

    def log_sync_session(self, action, dest_path, files):
        # Ensure current_session is not None
        if self.current_session is None:
            raise ValueError(
                "Logging session not started. Call 'start_session' before logging pull sessions."
            )

        session_summary = {
            "timestamp": datetime.now().isoformat(),
            "action": action,  # "synced" or "deleted"
            "destination": dest_path,
            "file_count": len(files),
            "files": files,
        }
        self.current_session["pull_sessions"].append(session_summary)

    def end_session(self):
        if self.current_session is None:
            raise ValueError("Logging session not started or already ended.")

        self.current_session["end_time"] = datetime.now().isoformat()
        self.current_session["session_duration"] = str(
            datetime.now() - datetime.fromisoformat(self.current_session["start_time"])
        )
        self.log_data["sessions"].append(self.current_session)
        self.save_log()  # Save log data after session end
        self.current_session = None  # Reset current_session after saving

    def save_log(self):
        with open(self.log_file, "w") as file:
            json.dump(self.log_data, file, indent=4)
