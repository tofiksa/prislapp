from minio import Minio

from app.config import settings


class StorageService:
    def __init__(self) -> None:
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

    def ensure_bucket(self) -> None:
        if not self.client.bucket_exists(settings.minio_bucket):
            self.client.make_bucket(settings.minio_bucket)

    def is_available(self) -> bool:
        try:
            self.client.bucket_exists(settings.minio_bucket)
            return True
        except Exception:
            return False
