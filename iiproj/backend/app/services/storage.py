import os
import time
from pathlib import Path
from flask import current_app

ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "txt", "md", "png", "jpg", "jpeg"}
MAX_FILE_BYTES = 10 * 1024 * 1024


def store_content(filename, content, content_type="application/octet-stream"):
    if len(content) > MAX_FILE_BYTES:
        raise ValueError("Files must be 10 MB or smaller.")
    extension = Path(filename).suffix.lower().lstrip(".")
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("This file type is not supported.")
    if all(current_app.config.get(key) for key in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET")):
        import cloudinary
        import cloudinary.uploader
        cloudinary.config(cloud_name=current_app.config["CLOUDINARY_CLOUD_NAME"], api_key=current_app.config["CLOUDINARY_API_KEY"], api_secret=current_app.config["CLOUDINARY_API_SECRET"], secure=True)
        result = cloudinary.uploader.upload(content, resource_type="raw", type="private", folder="academic-mentor", use_filename=True, unique_filename=True)
        return {"storageProvider": "cloudinary", "publicId": result["public_id"], "secureUrl": result["secure_url"], "contentType": content_type, "filename": Path(filename).name, "size": len(content)}
    target = Path(current_app.config["LOCAL_UPLOAD_DIR"]).resolve()
    target.mkdir(parents=True, exist_ok=True)
    path = target / (os.urandom(16).hex() + ("." + extension if extension else ""))
    path.write_bytes(content)
    return {"storageProvider": "local", "storagePath": str(path), "contentType": content_type, "filename": Path(filename).name, "size": len(content)}


def signed_download(record):
    if record.get("storageProvider") == "cloudinary":
        import cloudinary
        import cloudinary.utils
        cloudinary.config(cloud_name=current_app.config["CLOUDINARY_CLOUD_NAME"], api_key=current_app.config["CLOUDINARY_API_KEY"], api_secret=current_app.config["CLOUDINARY_API_SECRET"], secure=True)
        extension = Path(record.get("filename", "file")).suffix.lstrip(".") or None
        return cloudinary.utils.private_download_url(record["publicId"], extension, expires_at=int(time.time()) + 3600, attachment=True)
    return None


def delete_stored_file(record):
    if record.get("storageProvider") == "cloudinary" and record.get("publicId"):
        import cloudinary
        import cloudinary.uploader
        cloudinary.config(cloud_name=current_app.config["CLOUDINARY_CLOUD_NAME"], api_key=current_app.config["CLOUDINARY_API_KEY"], api_secret=current_app.config["CLOUDINARY_API_SECRET"], secure=True)
        cloudinary.uploader.destroy(record["publicId"], resource_type="raw", type="private")
    elif record.get("storageProvider") == "local" and record.get("storagePath"):
        Path(record["storagePath"]).unlink(missing_ok=True)
