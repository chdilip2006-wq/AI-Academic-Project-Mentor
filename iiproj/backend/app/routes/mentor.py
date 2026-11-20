from flask import Blueprint, g, jsonify
from ..agents.groq import generate_json, friendly_failure
from ..extensions import db
from ..middleware.auth import require_auth
from ..middleware.rate_limit import rate_limit
from ..services.store import now, project_for_user, serialize
from ..utils.validation import json_body, required_text

bp = Blueprint("mentor", __name__)


@bp.get("/projects/<project_id>/chat")
@require_auth("student")
def history(project_id):
    project_for_user(project_id, g.user, write=True)
    docs = db.collection("mentorChats").where("projectId", "==", project_id).where("ownerId", "==", g.user["uid"]).stream()
    return jsonify({"messages": sorted([serialize(d) for d in docs], key=lambda x: str(x.get("createdAt", "")))})


@bp.post("/projects/<project_id>/chat")
@rate_limit(20, 60)
@require_auth("student")
def chat(project_id):
    _, project = project_for_user(project_id, g.user, write=True)
    data = json_body(["message"])
    prompt = required_text(data, "message", 4000)
    recent = list(db.collection("mentorChats").where("projectId", "==", project_id).where("ownerId", "==", g.user["uid"]).stream())
    profile_snap = db.collection("studentProfiles").document(g.user["uid"]).get()
    progress = list(db.collection("progressUpdates").where("projectId", "==", project_id).stream())
    milestones = list(db.collection("milestones").where("projectId", "==", project_id).stream())
    try:
        response = generate_json("You are a supportive academic project mentor. Answer the student's latest question using the supplied profile, project blueprint, milestones, progress and previous conversation. Be clear and actionable. Do not claim project results or references. Return JSON with keys answer and suggestedNextSteps (array).", {"question": prompt, "profile": profile_snap.to_dict() if profile_snap.exists else {}, "project": project, "milestones": [m.to_dict() for m in milestones], "progress": [p.to_dict() for p in progress], "conversation": [d.to_dict() for d in recent[-12:]]})
    except Exception as error:
        return jsonify({"error": friendly_failure(error, "AI mentor")}), 503
    if not isinstance(response, dict) or not isinstance(response.get("answer"), str) or not isinstance(response.get("suggestedNextSteps", []), list):
        return jsonify({"error": "The AI mentor returned an invalid response. Please retry."}), 502
    timestamp = now()
    user_ref, ai_ref = db.collection("mentorChats").document(), db.collection("mentorChats").document()
    user_ref.set({"projectId": project_id, "ownerId": g.user["uid"], "role": "user", "content": prompt, "createdAt": timestamp})
    ai_ref.set({"projectId": project_id, "ownerId": g.user["uid"], "role": "assistant", "content": response.get("answer", ""), "suggestedNextSteps": response.get("suggestedNextSteps", []), "createdAt": timestamp})
    return jsonify({"reply": {"id": ai_ref.id, "role": "assistant", **response, "createdAt": timestamp.isoformat()}})
