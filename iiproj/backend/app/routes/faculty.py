from flask import Blueprint, g, jsonify
from ..extensions import db
from ..middleware.auth import require_auth
from ..middleware.rate_limit import rate_limit
from ..services.store import project_for_user, serialize

bp = Blueprint("faculty", __name__)


@bp.get("/faculty/dashboard")
@require_auth("faculty", "admin")
def dashboard():
    if g.user["role"] == "admin":
        assignments = list(db.collection("facultyAssignments").stream())
        projects = list(db.collection("projects").stream())
    else:
        assignments = list(db.collection("facultyAssignments").where("facultyId", "==", g.user["uid"]).stream())
        projects = [db.collection("projects").document(a.to_dict().get("projectId", "")).get() for a in assignments]
    rows = []
    for doc in projects:
        if not doc.exists:
            continue
        project = serialize(doc)
        user_doc = db.collection("users").document(project.get("ownerId", "")).get()
        project["student"] = user_doc.to_dict() if user_doc.exists else {"name": "Student"}
        rows.append(project)
    delayed = []
    for project in rows:
        project_milestones = db.collection("milestones").where("projectId", "==", project["id"]).stream()
        if any((milestone.to_dict() or {}).get("status") == "Delayed" for milestone in project_milestones):
            delayed.append(project)
    at_risk = [p for p in rows if p.get("health") == "At Risk" or p.get("planningStatus") == "failed"]
    in_progress = [p for p in rows if p.get("status", "").lower() in ("planned", "in progress")]
    completed = [p for p in rows if p.get("status", "").lower() == "completed"]
    return jsonify({"summary": {"assignedProjects": len(rows), "assignedStudents": len({p.get("ownerId") for p in rows if p.get("ownerId")}), "inProgress": len(in_progress), "completed": len(completed), "delayed": len(delayed), "atRisk": len(at_risk)}, "projects": rows})


@bp.get("/faculty/projects/<project_id>")
@require_auth("faculty", "admin")
def faculty_project(project_id):
    _, project = project_for_user(project_id, g.user)
    project["id"] = project_id
    milestones = [serialize(d) for d in db.collection("milestones").where("projectId", "==", project_id).stream()]
    progress = [serialize(d) for d in db.collection("progressUpdates").where("projectId", "==", project_id).stream()]
    summary = project.get("facultySummary") or "Generate an AI summary when you want a concise review of this project."
    return jsonify({"project": project, "milestones": milestones, "progressUpdates": progress, "aiSummary": summary, "summaryGeneratedAt": project.get("facultySummaryGeneratedAt")})


@bp.post("/faculty/projects/<project_id>/summary")
@rate_limit(6, 3600)
@require_auth("faculty", "admin")
def generate_faculty_summary(project_id):
    _, project = project_for_user(project_id, g.user)
    milestones = [serialize(item) for item in db.collection("milestones").where("projectId", "==", project_id).stream()]
    progress = [serialize(item) for item in db.collection("progressUpdates").where("projectId", "==", project_id).stream()]
    from ..agents.groq import generate_json
    try:
        result = generate_json("Summarize the student's project, progress, project health, and faculty attention points in 3-5 sentences. Use only supplied facts. Include existing risks where relevant; never invent completed work or results. Return JSON with key summary.", {"project": project, "milestones": milestones, "progress": progress, "risks": (project.get("blueprint") or {}).get("risks", {})})
    except Exception as error:
        message = str(error) if "Groq" in str(error) else "The faculty summary service is temporarily unavailable."
        return jsonify({"error": message}), 503
    if not isinstance(result, dict) or not isinstance(result.get("summary"), str):
        return jsonify({"error": "The faculty summary agent returned an invalid response. Please retry."}), 502
    from ..services.store import now
    saved_at = now()
    db.collection("projects").document(project_id).update({"facultySummary": result["summary"], "facultySummaryGeneratedAt": saved_at})
    return jsonify({"aiSummary": result["summary"], "summaryGeneratedAt": saved_at.isoformat()})
