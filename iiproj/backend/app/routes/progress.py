from flask import Blueprint, g, jsonify
from ..extensions import db
from ..middleware.auth import require_auth
from ..services.store import now, project_for_user, serialize
from ..services.health import refresh_project_health
from ..utils.validation import json_body

bp = Blueprint("progress", __name__)
STATUSES = {"Not Started", "In Progress", "Completed", "Delayed"}


@bp.get("/projects/<project_id>/milestones")
@require_auth("student", "faculty", "admin")
def milestones(project_id):
    project_for_user(project_id, g.user)
    docs = db.collection("milestones").where("projectId", "==", project_id).stream()
    return jsonify({"milestones": sorted([serialize(d) for d in docs], key=lambda x: x.get("order", 0))})


@bp.patch("/projects/<project_id>/milestones/<milestone_id>")
@require_auth("student")
def update_milestone(project_id, milestone_id):
    project_for_user(project_id, g.user, write=True)
    ref = db.collection("milestones").document(milestone_id)
    snap = ref.get()
    if not snap.exists or snap.to_dict().get("projectId") != project_id:
        return jsonify({"error": "Milestone not found."}), 404
    data = json_body()
    for key in ("description", "challenges"):
        if key in data and (not isinstance(data[key], str) or len(data[key]) > (3000 if key == "description" else 1500)):
            return jsonify({"error": f"{key} must be text within the allowed length."}), 400
    if "completedTasks" in data and (not isinstance(data["completedTasks"], list) or len(data["completedTasks"]) > 30 or any(not isinstance(task, str) or len(task) > 300 for task in data["completedTasks"])):
        return jsonify({"error": "Completed tasks must be a list of up to 30 short text items."}), 400
    if "dueDate" in data and (not isinstance(data["dueDate"], str) or len(data["dueDate"]) > 40):
        return jsonify({"error": "Due date must be a date string."}), 400
    changes = {k: data[k] for k in ("description", "completedTasks", "challenges", "dueDate") if k in data}
    if "status" in data:
        if data["status"] not in STATUSES:
            return jsonify({"error": "Invalid milestone status."}), 400
        changes["status"] = data["status"]
    if "progress" in data:
        try:
            progress = int(data["progress"])
        except (ValueError, TypeError):
            return jsonify({"error": "Progress must be a number from 0 to 100."}), 400
        if not 0 <= progress <= 100:
            return jsonify({"error": "Progress must be between 0 and 100."}), 400
        changes["progress"] = progress
        if progress == 100:
            changes["status"] = "Completed"
        elif progress > 0 and "status" not in changes:
            changes["status"] = "In Progress"
    changes["updatedAt"] = now()
    ref.update(changes)
    health = refresh_project_health(project_id) or {"overallProgress": 0, "health": "On Track"}
    return jsonify({"milestone": {**snap.to_dict(), **changes, "id": milestone_id}, "overallProgress": health["overallProgress"], "health": health["health"]})


@bp.post("/projects/<project_id>/progress")
@require_auth("student")
def create_progress(project_id):
    project_for_user(project_id, g.user, write=True)
    data = json_body(["summary"])
    if not isinstance(data["summary"], str) or not data["summary"].strip() or len(data["summary"]) > 3000:
        return jsonify({"error": "Summary is required and must be under 3000 characters."}), 400
    completed_tasks = data.get("completedTasks", [])
    if not isinstance(completed_tasks, list) or len(completed_tasks) > 30 or any(not isinstance(task, str) or len(task) > 300 for task in completed_tasks):
        return jsonify({"error": "Completed tasks must be a list of up to 30 short text items."}), 400
    challenges = data.get("challenges", "")
    if not isinstance(challenges, str) or len(challenges) > 1500:
        return jsonify({"error": "Challenges must be text under 1500 characters."}), 400
    week = data.get("week")
    if week not in (None, ""):
        try:
            week = int(week)
        except (ValueError, TypeError):
            return jsonify({"error": "Week must be a number from 1 to 52."}), 400
        if not 1 <= week <= 52:
            return jsonify({"error": "Week must be a number from 1 to 52."}), 400
    ref = db.collection("progressUpdates").document()
    report = {"projectId": project_id, "ownerId": g.user["uid"], "summary": data["summary"].strip(), "completedTasks": completed_tasks, "challenges": challenges, "week": week, "createdAt": now()}
    ref.set(report)
    health = refresh_project_health(project_id)
    return jsonify({"progressUpdate": {**report, "id": ref.id}, "projectHealth": health}), 201


@bp.get("/projects/<project_id>/progress")
@require_auth("student", "faculty", "admin")
def list_progress(project_id):
    project_for_user(project_id, g.user)
    docs = db.collection("progressUpdates").where("projectId", "==", project_id).stream()
    return jsonify({"progressUpdates": [serialize(d) for d in docs]})
