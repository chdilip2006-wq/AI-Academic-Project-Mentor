from datetime import datetime, timezone
from ..extensions import db
from ..utils.errors import ApiError


def now():
    return datetime.now(timezone.utc)


def project_for_user(project_id, user, write=False):
    ref = db.collection("projects").document(project_id)
    snap = ref.get()
    if not snap.exists:
        raise ApiError("Project not found.", 404)
    project = snap.to_dict()
    if user["role"] != "admin" and project.get("ownerId") != user["uid"]:
        assignment = db.collection("facultyAssignments").where("projectId", "==", project_id).where("facultyId", "==", user["uid"]).limit(1).stream()
        if write or user["role"] != "faculty" or not list(assignment):
            raise ApiError("You do not have access to this project.", 403)
    return ref, project


def serialize(doc):
    value = doc.to_dict() or {}
    value["id"] = doc.id
    for key, item in list(value.items()):
        if hasattr(item, "isoformat"):
            value[key] = item.isoformat()
    return value
