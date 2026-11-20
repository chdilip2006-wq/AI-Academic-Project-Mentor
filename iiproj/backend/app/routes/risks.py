from flask import Blueprint, g, jsonify
from ..agents.groq import generate_json, friendly_failure
from ..extensions import db
from ..middleware.auth import require_auth
from ..middleware.rate_limit import rate_limit
from ..services.store import now, project_for_user, serialize
from ..services.health import refresh_project_health
from ..utils.validation import json_body

bp = Blueprint("risks", __name__)


@bp.get("/projects/<project_id>/risks")
@require_auth("student", "faculty", "admin")
def list_risks(project_id):
    _, project = project_for_user(project_id, g.user)
    reports = [serialize(doc) for doc in db.collection("progressUpdates").where("projectId", "==", project_id).stream() if (doc.to_dict() or {}).get("challenges", "").strip()]
    assessments = [serialize(doc) for doc in db.collection("riskAssessments").where("projectId", "==", project_id).stream()]
    return jsonify({"risks": (project.get("blueprint") or {}).get("risks", {}).get("risks", []), "reportedChallenges": reports, "assessments": sorted(assessments, key=lambda row: row.get("createdAt", ""), reverse=True)})


@bp.post("/projects/<project_id>/risks/assess")
@rate_limit(6, 3600)
@require_auth("student")
def assess_risks(project_id):
    _, project = project_for_user(project_id, g.user, write=True)
    reports = list(db.collection("progressUpdates").where("projectId", "==", project_id).stream())
    milestones = list(db.collection("milestones").where("projectId", "==", project_id).stream())
    try:
        result = generate_json("You are the project's risk assessment agent. Reassess current execution risks using only the stored blueprint and progress. Distinguish known risks from reported challenges; never invent events. Return JSON with keys summary and risks. Each risk must contain category, description, severity (Low/Medium/High), probability (Low/Medium/High), and mitigation.", {"project": project, "existingRisks": (project.get("blueprint") or {}).get("risks", {}).get("risks", []), "milestones": [item.to_dict() for item in milestones], "progressUpdates": [item.to_dict() for item in reports]})
    except Exception as error:
        return jsonify({"error": friendly_failure(error, "risk assessment")}), 503
    if not isinstance(result, dict) or not isinstance(result.get("summary"), str) or not isinstance(result.get("risks"), list):
        return jsonify({"error": "The risk agent returned an invalid response. Please retry."}), 502
    required = ("category", "description", "severity", "probability", "mitigation")
    for risk in result["risks"]:
        if not isinstance(risk, dict) or any(not isinstance(risk.get(key), str) for key in required) or risk.get("severity") not in ("Low", "Medium", "High") or risk.get("probability") not in ("Low", "Medium", "High"):
            return jsonify({"error": "The risk agent returned an invalid risk item. Please retry."}), 502
    record = {"projectId": project_id, "ownerId": g.user["uid"], "summary": result["summary"], "risks": result["risks"], "createdAt": now()}
    ref = db.collection("riskAssessments").document(); ref.set(record)
    refresh_project_health(project_id)
    return jsonify({"assessment": {**record, "id": ref.id}}), 201
