from io import BytesIO

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

    def upload_receipt(
        self,
        object_name: str,
        data: bytes,
        content_type: str = "image/jpeg",
    ) -> str:
        self.client.put_object(
            settings.minio_bucket,
            object_name,
            BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return object_name

    def download_receipt(self, object_name: str) -> bytes:
        response = self.client.get_object(settings.minio_bucket, object_name)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()
