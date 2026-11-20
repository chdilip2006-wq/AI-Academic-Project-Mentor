from flask import Blueprint, g, jsonify
from ..extensions import db
from ..middleware.auth import require_auth
from ..services.store import now, serialize
from ..utils.validation import json_body

bp = Blueprint("admin", __name__)


@bp.get("/admin/overview")
@require_auth("admin")
def overview():
    users = [doc.to_dict() or {} for doc in db.collection("users").stream()]
    projects = [doc.to_dict() or {} for doc in db.collection("projects").stream()]
    return jsonify({"overview": {
        "totalUsers": len(users),
        "students": sum(user.get("role") == "student" for user in users),
        "faculty": sum(user.get("role") == "faculty" for user in users),
        "admins": sum(user.get("role") == "admin" for user in users),
        "totalProjects": len(projects),
        "inProgress": sum((item.get("status") or "").lower() in ("planned", "in progress") for item in projects),
        "completed": sum((item.get("status") or "").lower() == "completed" for item in projects),
        "atRisk": sum(item.get("health") == "At Risk" for item in projects),
        "needsAttention": sum(item.get("health") == "Needs Attention" for item in projects),
    }})


@bp.get("/admin/users")
@require_auth("admin")
def list_users():
    users = []
    for doc in db.collection("users").stream():
        item = doc.to_dict() or {}
        item["uid"] = doc.id
        item.pop("passwordHash", None)
        users.append(item)
    return jsonify({"users": users})


@bp.patch("/admin/users/<uid>/role")
@require_auth("admin")
def set_role(uid):
    data = json_body(["role"])
    if uid == g.user["uid"]:
        return jsonify({"error": "You cannot change your own role."}), 403
    if data["role"] == "faculty":
        return jsonify({"error": "Faculty access can only be granted by approving a pending faculty request."}), 409
    if data["role"] not in ("student", "admin"):
        return jsonify({"error": "Role must be student or admin. Faculty access requires request approval."}), 400
    ref = db.collection("users").document(uid)
    snapshot = ref.get()
    if not snapshot.exists:
        return jsonify({"error": "User not found."}), 404
    ref.update({"role": data["role"], "facultyAccessRequestStatus": None, "updatedAt": now()})
    if snapshot.to_dict().get("role") == "faculty" and data["role"] != "faculty":
        for assignment in db.collection("facultyAssignments").where("facultyId", "==", uid).stream():
            db.collection("facultyAssignments").document(assignment.id).delete()
    for request_doc in db.collection("facultyAccessRequests").where("userId", "==", uid).where("status", "==", "PENDING").stream():
        db.collection("facultyAccessRequests").document(request_doc.id).update({"status": "REJECTED", "reviewedBy": g.user["uid"], "reviewedAt": now(), "reviewNote": "Closed because account role changed."})
    return jsonify({"message": "User role updated.", "uid": uid, "role": data["role"]})


@bp.get("/admin/faculty-requests")
@require_auth("admin")
def faculty_access_requests():
    rows = [serialize(doc) for doc in db.collection("facultyAccessRequests").stream()]
    rows.sort(key=lambda item: item.get("createdAt", ""), reverse=True)
    return jsonify({"requests": rows})


@bp.post("/admin/faculty-requests/<request_id>/review")
@require_auth("admin")
def review_faculty_access_request(request_id):
    data = json_body(["decision"])
    decision = data["decision"]
    if decision not in ("APPROVED", "REJECTED"):
        return jsonify({"error": "Decision must be APPROVED or REJECTED."}), 400
    request_ref = db.collection("facultyAccessRequests").document(request_id)
    request_snap = request_ref.get()
    if not request_snap.exists:
        return jsonify({"error": "Faculty access request not found."}), 404
    faculty_request = request_snap.to_dict()
    if faculty_request.get("status") != "PENDING":
        return jsonify({"error": "This faculty access request has already been reviewed."}), 409
    user_ref = db.collection("users").document(faculty_request.get("userId", ""))
    user_snap = user_ref.get()
    if not user_snap.exists or user_snap.to_dict().get("role") != "student":
        return jsonify({"error": "The request no longer belongs to an eligible student account."}), 409
    timestamp = now()
    request_ref.update({"status": decision, "reviewedBy": g.user["uid"], "reviewedAt": timestamp, "updatedAt": timestamp})
    next_role = "faculty" if decision == "APPROVED" else "student"
    user_ref.update({"role": next_role, "facultyAccessRequestStatus": decision, "updatedAt": timestamp})
    return jsonify({"message": f"Faculty access request {decision.lower()}.", "userId": faculty_request["userId"], "role": next_role, "status": decision})


@bp.post("/admin/assignments")
@require_auth("admin")
def assign_faculty():
    data = json_body(["facultyId", "projectId"])
    faculty = db.collection("users").document(str(data["facultyId"])).get()
    project = db.collection("projects").document(str(data["projectId"])).get()
    if not faculty.exists or faculty.to_dict().get("role") != "faculty" or not project.exists:
        return jsonify({"error": "Choose an existing faculty user and project."}), 400
    existing = db.collection("facultyAssignments").where("facultyId", "==", str(data["facultyId"])).where("projectId", "==", str(data["projectId"])).limit(1).stream()
    if existing:
        return jsonify({"message": "Faculty assignment already exists."}), 200
    ref = db.collection("facultyAssignments").document()
    ref.set({"facultyId": str(data["facultyId"]), "studentId": project.to_dict().get("ownerId"), "projectId": str(data["projectId"]), "assignedBy": g.user["uid"], "createdAt": now()})
    return jsonify({"message": "Faculty assignment saved."}), 201


@bp.get("/admin/assignments")
@require_auth("admin")
def list_assignments():
    rows = []
    for doc in db.collection("facultyAssignments").stream():
        assignment = serialize(doc)
        faculty = db.collection("users").document(assignment.get("facultyId", "")).get()
        project = db.collection("projects").document(assignment.get("projectId", "")).get()
        student_id = assignment.get("studentId") or ((project.to_dict() or {}).get("ownerId") if project.exists else "")
        student = db.collection("users").document(student_id or "").get()
        rows.append({**assignment, "faculty": (faculty.to_dict() or {}).get("name", "Faculty") if faculty.exists else "Faculty", "student": (student.to_dict() or {}).get("name", "Student") if student.exists else "Student", "project": (project.to_dict() or {}).get("title", "Project") if project.exists else "Project"})
    return jsonify({"assignments": rows})


@bp.delete("/admin/assignments/<assignment_id>")
@require_auth("admin")
def delete_assignment(assignment_id):
    ref = db.collection("facultyAssignments").document(assignment_id)
    if not ref.get().exists:
        return jsonify({"error": "Assignment not found."}), 404
    ref.delete()
    return jsonify({"message": "Faculty assignment removed."})


@bp.get("/admin/settings")
@require_auth("admin")
def settings():
    docs = db.collection("platformSettings").where("key", "==", "general").limit(1).stream()
    return jsonify({"settings": docs[0].to_dict() if docs else {"maintenanceMode": False, "platformName": "AI Academic Project Mentor"}})


@bp.put("/admin/settings")
@require_auth("admin")
def update_settings():
    data = json_body()
    allowed = {"maintenanceMode", "platformName", "supportEmail"}
    settings = {k: data[k] for k in data if k in allowed}
    if "platformName" in settings and (not isinstance(settings["platformName"], str) or len(settings["platformName"]) > 100):
        return jsonify({"error": "Platform name must be under 100 characters."}), 400
    settings["updatedAt"] = now()
    docs = db.collection("platformSettings").where("key", "==", "general").limit(1).stream()
    ref = db.collection("platformSettings").document(docs[0].id) if docs else db.collection("platformSettings").document()
    ref.set({**settings, "key": "general"}, merge=True)
    return jsonify({"settings": settings})
