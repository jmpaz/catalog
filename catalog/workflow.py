from catalog.media import MediaObject


class Library:
    def __init__(self):
        self.media_objects = []

    def import_media_object(self, file_path, media_object_class):
        if issubclass(media_object_class, MediaObject):
            media_object = media_object_class(file_path)
            self.media_objects.append(media_object)
            return media_object
        else:
            raise ValueError("media_object_class must be a subclass of MediaObject")


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
