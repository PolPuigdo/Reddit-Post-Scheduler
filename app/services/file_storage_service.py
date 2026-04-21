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
            raise ValueError("Formato de imagen no permitido. Usa jpg, jpeg, png o webp.")

        unique_name = f"{uuid4().hex}{extension}"
        final_path = self.upload_folder / unique_name

        file.save(final_path)

        return str(final_path)