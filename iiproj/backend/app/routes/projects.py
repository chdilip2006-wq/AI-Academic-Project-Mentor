from flask import Blueprint, g, jsonify
from ..extensions import db
from ..middleware.auth import require_auth
from ..services.store import now, project_for_user, serialize
from ..utils.validation import json_body, required_text

bp = Blueprint("projects", __name__)


@bp.get("/projects")
@require_auth("student", "faculty", "admin")
def list_projects():
    if g.user["role"] == "student":
        docs = db.collection("projects").where("ownerId", "==", g.user["uid"]).stream()
    elif g.user["role"] == "admin":
        docs = db.collection("projects").stream()
    else:
        assignments = list(db.collection("facultyAssignments").where("facultyId", "==", g.user["uid"]).stream())
        ids = {a.to_dict().get("projectId") for a in assignments}
        docs = [db.collection("projects").document(pid).get() for pid in ids if pid]
    return jsonify({"projects": [serialize(doc) for doc in docs if doc.exists]})


@bp.post("/projects")
@require_auth("student")
def create_project():
    data = json_body(["title", "idea"])
    title, idea = required_text(data, "title", 140), required_text(data, "idea", 3000, 10)
    ref = db.collection("projects").document()
    project = {"ownerId": g.user["uid"], "studentId": g.user["uid"], "facultyId": None, "title": title, "idea": idea, "domain": str(data.get("domain", ""))[:100], "status": "submitted", "planningStatus": "pending", "overallProgress": 0, "health": "On Track", "createdAt": now(), "updatedAt": now()}
    ref.set(project)
    return jsonify({"project": {**project, "id": ref.id}}), 201


@bp.get("/projects/<project_id>")
@require_auth("student", "faculty", "admin")
def get_project(project_id):
    _, project = project_for_user(project_id, g.user)
    project["id"] = project_id
    return jsonify({"project": project})


@bp.patch("/projects/<project_id>")
@require_auth("student")
def update_project(project_id):
    ref, project = project_for_user(project_id, g.user, write=True)
    if project.get("status") == "completed":
        return jsonify({"error": "Completed projects cannot be edited."}), 409
    data = json_body()
    changes = {}
    if "title" in data:
        changes["title"] = required_text(data, "title", 140)
    if "idea" in data:
        changes["idea"] = required_text(data, "idea", 3000, 10)
    if changes:
        changes["updatedAt"] = now()
        ref.update(changes)
    return jsonify({"project": {**project, **changes, "id": project_id}})
