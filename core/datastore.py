import json
import os
import shutil
from pathlib import Path


class Datastore:
    def __init__(self, datastore_file="data/datastore.json", files_dir="data/files"):
        self.datastore_file = datastore_file
        self.files_dir = files_dir
        Path(self.files_dir).mkdir(parents=True, exist_ok=True)
        if not os.path.exists(self.datastore_file):
            with open(self.datastore_file, "w") as file:
                json.dump({}, file)

    def _load_datastore(self):
        with open(self.datastore_file, "r") as file:
            return json.load(file)

    def _save_datastore(self, datastore):
        with open(self.datastore_file, "w") as file:
            json.dump(datastore, file, indent=4)

    def _generate_unique_id(self, datastore):
        return str(max([int(k) for k in datastore.keys()] + [0]) + 1)

    def _generate_unique_name(self, datastore, name):
        original_name = name
        count = 1
        while name in [data["name"] for data in datastore.values()]:
            name = f"{original_name}_{count}"
            count += 1
        return name

    def add(self, filepath, name=None, symlink=False):
        datastore = self._load_datastore()
        if any(data["path_src"] == filepath for data in datastore.values()):
            raise FileExistsError(f"File at {filepath} is already in the datastore.")

        file_id = self._generate_unique_id(datastore)
        filename = Path(filepath).name
        name = name if name else filename
        name = self._generate_unique_name(datastore, name)

        target_path = os.path.join(self.files_dir, name)
        if symlink:
            os.symlink(filepath, target_path)
        else:
            shutil.copy(filepath, target_path)

        datastore[file_id] = {
            "id": file_id,
            "name": name,
            "type": "audio",  # Default type; can be updated later
            "path": target_path,
            "path_src": filepath,
        }

        self._save_datastore(datastore)
        return file_id

    def get(self, id=None, name=None):
        datastore = self._load_datastore()
        for file_id, data in datastore.items():
            if (id and data["id"] == id) or (name and data["name"] == name):
                return data
        raise ValueError("No file with the given ID or name found in the datastore.")
