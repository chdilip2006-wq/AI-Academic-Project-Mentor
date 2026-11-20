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
    db.collection("studentProfiles").document(ref.id).set({"uid": ref.id, "skills": []})
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
