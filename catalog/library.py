import os
from catalog.media import MediaObject


class Library:
    def __init__(self):
        self.media_objects = []

    def import_media_object(
        self, file_path=None, media_object_class=None, name=None, url=None
    ):
        if issubclass(media_object_class, MediaObject):
            media_object = media_object_class(file_path=file_path, url=url, name=name)
            self.media_objects.append(media_object)
            return media_object
        else:
            raise ValueError("media_object_class must be a subclass of MediaObject")

    def create_pointer(self, media_object, dest_path="data/pointers"):
        id = media_object.id
        name = media_object.name if media_object.name else None
        obj_type = media_object.__class__.__name__
        frontmatter = f"""---
id:
- {id}
tags:
- media/{obj_type.lower()}
---"""
        body = media_object.text if media_object.text else ""
        content = f"{frontmatter}\n{body}" if body else frontmatter

        filename = name if name else id

        self.write_file(dest_path, filename, content)

    @staticmethod
    def write_file(path, name, content):
        path = path
        os.makedirs(path, exist_ok=True)
        with open(f"{path}/{name}.md", "w") as file:
            file.write(content)


class Job:
    def __init__(self):
        self.tasks = []

    def add_task(self, task):
        if not callable(task):
            raise ValueError("task must be a callable")
        self.tasks.append(task)

    def execute(self, media_object):
        for task in self.tasks:
            task(media_object)
