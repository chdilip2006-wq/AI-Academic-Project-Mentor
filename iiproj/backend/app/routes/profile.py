from flask import Blueprint, g, jsonify
from ..extensions import db
from ..middleware.auth import require_auth
from ..services.store import now
from ..utils.validation import json_body, required_text

bp = Blueprint("profile", __name__)


@bp.get("/profile")
@require_auth("student")
def get_profile():
    snap = db.collection("studentProfiles").document(g.user["uid"]).get()
    profile = snap.to_dict() if snap.exists else {"uid": g.user["uid"], "skills": [], "programmingLanguages": [], "previousProjectExperience": ""}
    return jsonify({"profile": profile})


@bp.put("/profile")
@require_auth("student")
def save_profile():
    data = json_body()
    profile = {key: data.get(key, "") for key in ("rollNumber", "department", "year", "bio", "interests", "github", "program", "previousProjectExperience")}
    for key, maximum in (("rollNumber", 40), ("department", 120), ("bio", 1000), ("interests", 500), ("github", 250), ("previousProjectExperience", 2000)):
        if not isinstance(profile[key], str) or len(profile[key]) > maximum:
            return jsonify({"error": f"{key} is too long or invalid."}), 400
    try:
        profile["year"] = int(profile["year"]) if profile["year"] != "" else ""
    except (ValueError, TypeError):
        return jsonify({"error": "Year must be a number."}), 400
    skills = data.get("skills", [])
    if not isinstance(skills, list) or len(skills) > 40:
        return jsonify({"error": "Skills must be a list with at most 40 entries."}), 400
    clean = []
    for item in skills:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or item.get("level") not in ("Beginner", "Intermediate", "Advanced"):
            return jsonify({"error": "Each skill needs a name and Beginner, Intermediate, or Advanced level."}), 400
        clean.append({"name": item["name"].strip()[:50], "level": item["level"]})
    languages = data.get("programmingLanguages", [])
    if not isinstance(languages, list) or len(languages) > 30 or any(not isinstance(item, str) or not item.strip() or len(item) > 50 for item in languages):
        return jsonify({"error": "Programming languages must be a list of up to 30 short names."}), 400
    languages = list(dict.fromkeys(item.strip() for item in languages))
    profile.update({"uid": g.user["uid"], "skills": clean, "programmingLanguages": languages, "updatedAt": now()})
    db.collection("studentProfiles").document(g.user["uid"]).set(profile, merge=True)
    return jsonify({"profile": profile})
