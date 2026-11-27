from datetime import datetime, timezone, timedelta
import re
import bcrypt
import jwt
from flask import Blueprint, current_app, g, jsonify
from pymongo.errors import DuplicateKeyError
from ..extensions import db
from ..middleware.auth import require_auth
from ..middleware.rate_limit import rate_limit
from ..utils.validation import json_body, required_text

bp = Blueprint("auth", __name__)


def issue_token(user):
    now = datetime.now(timezone.utc)
    token = jwt.encode({"sub": user["uid"], "iat": now, "exp": now + timedelta(seconds=current_app.config["JWT_ACCESS_TOKEN_EXPIRES"])}, current_app.config["SECRET_KEY"], algorithm="HS256")
    return token


def public_user(user):
    keys = ("uid", "email", "name", "role", "facultyAccessRequestStatus")
    return {key: user[key] for key in keys if key in user}


def _registration_profile(data):
    profile = data.get("profile")
    if not isinstance(profile, dict):
        return None, "Complete your academic profile before creating an account."
    required = ("rollNumber", "department", "program", "year", "bio", "interests")
    labels = {"rollNumber": "roll number", "department": "department", "program": "program", "year": "academic year", "bio": "short bio", "interests": "areas of interest"}
    limits = {"rollNumber": 40, "department": 120, "program": 120, "bio": 1000, "interests": 500}
    cleaned = {}
    for key in required:
        value = profile.get(key)
        if key == "year":
            if not isinstance(value, (str, int)) or isinstance(value, bool):
                return None, "Enter your academic year."
        elif not isinstance(value, str):
            return None, f"Enter your {labels[key]}."
        value = str(value).strip()
        maximum = limits.get(key)
        if not value or (maximum is not None and len(value) > maximum):
            return None, f"Enter a valid {labels[key]}."
        cleaned[key] = value
    try:
        year = int(cleaned["year"])
    except ValueError:
        return None, "Academic year must be between 1 and 5."
    if year < 1 or year > 5:
        return None, "Academic year must be between 1 and 5."
    cleaned["year"] = year

    skills = profile.get("skills")
    if not isinstance(skills, list) or not skills or len(skills) > 40:
        return None, "Add at least one skill before creating your account."
    cleaned_skills = []
    seen_skills = set()
    for skill in skills:
        if not isinstance(skill, dict) or not isinstance(skill.get("name"), str) or skill.get("level") not in ("Beginner", "Intermediate", "Advanced"):
            return None, "Each skill needs a name and Beginner, Intermediate, or Advanced level."
        name = skill["name"].strip()
        if not name or len(name) > 50:
            return None, "Skill names must contain 1 to 50 characters."
        if name.casefold() not in seen_skills:
            cleaned_skills.append({"name": name, "level": skill["level"]})
            seen_skills.add(name.casefold())
    if not cleaned_skills:
        return None, "Add at least one skill before creating your account."
    cleaned["skills"] = cleaned_skills

    languages = profile.get("programmingLanguages", [])
    if not isinstance(languages, list) or len(languages) > 30 or any(not isinstance(item, str) or not item.strip() or len(item.strip()) > 50 for item in languages):
        return None, "Programming languages must be short names, with up to 30 entries."
    cleaned["programmingLanguages"] = list(dict.fromkeys(item.strip() for item in languages))
    for key, maximum in (("github", 250), ("previousProjectExperience", 2000)):
        value = profile.get(key, "")
        if not isinstance(value, str) or len(value) > maximum:
            return None, f"{key} is too long or invalid."
        cleaned[key] = value.strip()
    return cleaned, None


@bp.post("/auth/register")
@rate_limit(5, 3600)
def register():
    data = json_body(["name", "email", "password"])
    name = required_text(data, "name", 120)
    email = required_text(data, "email", 254).lower()
    password = data.get("password")
    requested_role = data.get("role")
    if requested_role not in (None, "student"):
        return jsonify({"error": "Public registration creates student accounts. Request faculty access for admin approval."}), 400
    request_faculty = data.get("requestFacultyAccess", False)
    if not isinstance(request_faculty, bool):
        return jsonify({"error": "requestFacultyAccess must be true or false."}), 400
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        return jsonify({"error": "Enter a valid email address."}), 400
    if not isinstance(password, str) or len(password) < 8 or len(password.encode("utf-8")) > 72:
        return jsonify({"error": "Password must be between 8 and 72 characters."}), 400
    profile, profile_error = _registration_profile(data)
    if profile_error:
        return jsonify({"error": profile_error}), 400
    role = "student"
    ref = db.collection("users").document()
    created_at = datetime.now(timezone.utc)
    user = {"uid": ref.id, "email": email, "name": name, "role": role, "passwordHash": bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(), "createdAt": created_at, "updatedAt": created_at}
    if request_faculty:
        user["facultyAccessRequestStatus"] = "PENDING"
    try:
        ref.set(user)
    except DuplicateKeyError:
        return jsonify({"error": "An account already uses that email."}), 409
    try:
        db.collection("studentProfiles").document(ref.id).set({**profile, "uid": ref.id, "createdAt": created_at, "updatedAt": created_at})
    except Exception:
        ref.delete()
        raise
    if request_faculty:
        db.collection("facultyAccessRequests").document().set({"userId": ref.id, "name": name, "email": email, "status": "PENDING", "createdAt": created_at, "updatedAt": created_at})
    safe = public_user(user)
    return jsonify({"token": issue_token(safe), "user": safe}), 201


@bp.post("/auth/faculty-access-request")
@require_auth("student")
def request_faculty_access():
    if g.user.get("role") != "student":
        return jsonify({"error": "Only student accounts can request faculty access."}), 403
    if g.user.get("facultyAccessRequestStatus") == "PENDING":
        return jsonify({"error": "Your faculty access request is already pending."}), 409
    timestamp = datetime.now(timezone.utc)
    request_ref = db.collection("facultyAccessRequests").document()
    record = {"userId": g.user["uid"], "name": g.user.get("name", ""), "email": g.user.get("email", ""), "status": "PENDING", "createdAt": timestamp, "updatedAt": timestamp}
    request_ref.set(record)
    db.collection("users").document(g.user["uid"]).update({"facultyAccessRequestStatus": "PENDING", "updatedAt": timestamp})
    return jsonify({"request": {**record, "id": request_ref.id}, "message": "Faculty access request submitted for admin review."}), 201


@bp.post("/auth/login")
@rate_limit(10, 900)
def login():
    data = json_body(["email", "password"])
    email = str(data.get("email", "")).strip().lower()
    user_doc = db.collection("users").collection.find_one({"email": email})
    password = data.get("password", "")
    if not user_doc or not isinstance(password, str) or len(password.encode("utf-8")) > 72 or not bcrypt.checkpw(password.encode(), user_doc.get("passwordHash", "").encode()):
        return jsonify({"error": "The email or password is incorrect."}), 401
    user = {**user_doc, "uid": str(user_doc["_id"])}
    safe = public_user(user)
    return jsonify({"token": issue_token(safe), "user": safe})


@bp.get("/auth/me")
@require_auth()
def me(): return jsonify({"user": public_user(g.user)})


@bp.patch("/auth/me")
@require_auth()
def update_me():
    name = required_text(json_body(), "name", 120)
    db.collection("users").document(g.user["uid"]).update({"name": name, "updatedAt": datetime.now(timezone.utc)})
    return jsonify({"user": {**public_user(g.user), "name": name}})
