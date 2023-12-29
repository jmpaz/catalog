import json
import os
from datetime import datetime


class Logger:
    def __init__(self, log_file):
        self.log_file = log_file
        self.log_data = {"session_start": None, "commands": []}

    def log_session_start(self, args):
        args_dict = {
            k: str(v) for k, v in vars(args).items() if k != "func"
        }  # Convert all args to strings, ommitting 'func'
        self.log_data["session_start"] = {
            "timestamp": datetime.now().isoformat(),
            "arguments": args_dict,
        }

    def log_whisperx_call(self, file_path, additional_info):
        self.log_data["commands"].append(
            {
                "timestamp": datetime.now().isoformat(),
                "file": file_path,
                "details": additional_info,
            }
        )

    def save_log(self):
        if not os.path.exists(os.path.dirname(self.log_file)):
            os.makedirs(os.path.dirname(self.log_file))
        with open(self.log_file, "w") as file:
            json.dump(self.log_data, file, indent=4)
