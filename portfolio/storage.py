from django.core.files.storage import FileSystemStorage, storages
from storages.backends.s3 import S3Storage


class PrivateFileSystemStorage(FileSystemStorage):
    def url(self, name):
        raise ValueError("Source originals have no public URL.")


class PrivateS3Storage(S3Storage):
    def url(self, name, **kwargs):
        raise ValueError("Source originals have no public URL.")


def original_storage():
    return storages["originals"]
