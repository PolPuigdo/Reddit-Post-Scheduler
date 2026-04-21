from pathlib import Path
from uuid import uuid4
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

class FileStorageService:
    ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

    def __init__(self, upload_folder: str):
        self.upload_folder = Path(upload_folder)
        self.upload_folder.mkdir(parents=True, exist_ok=True)

    def save_image(self, file: FileStorage) -> str:
        original_name = file.filename or ""
        safe_name = secure_filename(original_name)

        extension = Path(safe_name).suffix.lower()
        if extension not in self.ALLOWED_EXTENSIONS:
            raise ValueError("Unsupported image format. Please use jpg, jpeg, png, or webp.")

        unique_name = f"{uuid4().hex}{extension}"
        final_path = self.upload_folder / unique_name

        file.save(final_path)

        return str(final_path)

    def delete_image(self, image_path: str | None) -> None:
        if not image_path:
            return

        candidate = Path(image_path)
        if not candidate.is_absolute():
            candidate = self.upload_folder / candidate

        resolved_candidate = candidate.resolve(strict=False)
        resolved_upload_folder = self.upload_folder.resolve(strict=True)

        # Prevent accidental deletion outside configured uploads folder.
        try:
            resolved_candidate.relative_to(resolved_upload_folder)
        except ValueError as ex:
            raise ValueError("Refusing to delete image outside upload folder.") from ex

        if not resolved_candidate.exists():
            return

        resolved_candidate.unlink()
