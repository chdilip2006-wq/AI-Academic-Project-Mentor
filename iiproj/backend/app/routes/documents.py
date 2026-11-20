from flask import Blueprint, current_app, g, jsonify, request
from ..agents.groq import generate_json, friendly_failure
from ..extensions import db
from ..middleware.auth import require_auth
from ..middleware.rate_limit import rate_limit
from ..services.store import now, project_for_user, serialize
from ..utils.validation import json_body
from ..services.storage import store_content, delete_stored_file, signed_download

bp = Blueprint("documents", __name__)
DOCUMENT_TYPES = {"synopsis", "problem-statement", "objectives", "literature-review-outline", "methodology", "system-requirements", "progress-report", "final-report-outline"}


def public_metadata(record, document_id):
    return {key: record[key] for key in ("projectId", "type", "title", "filename", "contentType", "size", "createdAt") if key in record} | {"id": document_id}


@bp.post("/projects/<project_id>/documents")
@rate_limit(15, 3600)
@require_auth("student")
def generate_document(project_id):
    _, project = project_for_user(project_id, g.user, write=True)
    data = json_body(["type"])
    doc_type = data["type"]
    if doc_type not in DOCUMENT_TYPES:
        return jsonify({"error": "Choose a supported document type."}), 400
    updates = list(db.collection("progressUpdates").where("projectId", "==", project_id).stream()) if doc_type == "progress-report" else []
    try:
        result = generate_json("You are an academic writing assistant. Draft the requested academic project document using only supplied facts. Never invent findings, experimental data, citations or references. Mark missing facts as [To be completed by student]. Return JSON with key title and content (plain text or Markdown).", {"documentType": doc_type, "project": project, "progressUpdates": [u.to_dict() for u in updates]})
    except Exception as error:
        return jsonify({"error": friendly_failure(error, "document generator")}), 503
    if not isinstance(result, dict):
        return jsonify({"error": "The document generator returned an invalid result. Please retry."}), 502
    content = result.get("content")
    if not isinstance(content, str) or not content.strip():
        return jsonify({"error": "The document generator returned an invalid result. Please retry."}), 502
    try:
        stored = store_content(f"{doc_type}-{int(now().timestamp())}.md", content.encode("utf-8"), "text/markdown; charset=utf-8")
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    ref = db.collection("generatedDocuments").document()
    record = {"projectId": project_id, "ownerId": g.user["uid"], "type": doc_type, "title": str(result.get("title", doc_type.replace("-", " ").title()))[:180], **stored, "createdAt": now()}
    ref.set(record)
    return jsonify({"document": {**public_metadata(record, ref.id), "preview": content}}), 201


@bp.get("/projects/<project_id>/documents")
@require_auth("student", "faculty")
def list_documents(project_id):
    project_for_user(project_id, g.user, write=True)
    query = db.collection("generatedDocuments").where("projectId", "==", project_id)
    if g.user["role"] == "student": query = query.where("ownerId", "==", g.user["uid"])
    docs = query.stream()
    return jsonify({"documents": [public_metadata(d.to_dict(), d.id) for d in docs]})


@bp.get("/projects/<project_id>/documents/<document_id>/download")
@require_auth("student", "faculty")
def download_document(project_id, document_id):
    project_for_user(project_id, g.user)
    snap = db.collection("generatedDocuments").document(document_id).get()
    if not snap.exists or snap.to_dict().get("projectId") != project_id:
        return jsonify({"error": "Document not found."}), 404
    record = snap.to_dict()
    if record.get("storageProvider") == "cloudinary":
        try: return jsonify({"downloadUrl": signed_download(record), "expiresInSeconds": 3600})
        except Exception as error:
            current_app.logger.warning("Cloudinary signed download failed: %s", type(error).__name__)
            return jsonify({"error": "The document download link could not be created."}), 503
    return jsonify({"downloadUrl": f"/api/projects/{project_id}/documents/{document_id}/content", "expiresInSeconds": 3600})


@bp.get("/projects/<project_id>/documents/<document_id>/content")
@require_auth("student", "faculty")
def local_document_content(project_id, document_id):
    from flask import send_file
    from pathlib import Path
    project_for_user(project_id, g.user)
    snap = db.collection("generatedDocuments").document(document_id).get()
    record = snap.to_dict() if snap.exists else {}
    if record.get("projectId") != project_id or record.get("storageProvider") != "local":
        return jsonify({"error": "Document not found."}), 404
    path = Path(record.get("storagePath", "")).resolve()
    root = Path(current_app.config["LOCAL_UPLOAD_DIR"]).resolve()
    if root not in path.parents or not path.is_file(): return jsonify({"error": "Document not found."}), 404
    return send_file(path, mimetype=record.get("contentType", "application/octet-stream"), as_attachment=True, download_name=record.get("filename", "document"))


@bp.post("/projects/<project_id>/files")
@rate_limit(30, 3600)
@require_auth("student")
def upload_project_file(project_id):
    project_for_user(project_id, g.user, write=True)
    uploaded = request.files.get("file")
    if not uploaded: return jsonify({"error": "Choose a file to upload."}), 400
    try: stored = store_content(uploaded.filename or "upload", uploaded.read(), uploaded.mimetype or "application/octet-stream")
    except ValueError as error: return jsonify({"error": str(error)}), 400
    record = {"projectId": project_id, "ownerId": g.user["uid"], "type": "supporting-file", **stored, "createdAt": now()}
    ref = db.collection("generatedDocuments").document(); ref.set(record)
    return jsonify({"document": public_metadata(record, ref.id)}), 201


@bp.delete("/projects/<project_id>/documents/<document_id>")
@require_auth("student")
def delete_document(project_id, document_id):
    project_for_user(project_id, g.user, write=True)
    ref = db.collection("generatedDocuments").document(document_id)
    snap = ref.get(); record = snap.to_dict() if snap.exists else {}
    if record.get("projectId") != project_id or record.get("ownerId") != g.user["uid"]:
        return jsonify({"error": "Document not found."}), 404
    try: delete_stored_file(record)
    except Exception as error:
        current_app.logger.warning("Stored file deletion failed: %s", type(error).__name__)
        return jsonify({"error": "The file could not be deleted from storage."}), 503
    ref.delete()
    return jsonify({"message": "Document deleted."})
