import sys
from io import BytesIO
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bcrypt
import mongomock
import jwt
import pytest
from datetime import datetime, timedelta, timezone
from app import create_app


def client(extra_config=None):
    database = mongomock.MongoClient().testdb
    config = {"TESTING": True, "SECRET_KEY": "test-secret-key-long-enough-for-tests", "MONGO_DATABASE": database, "JWT_ACCESS_TOKEN_EXPIRES": 3600, "FRONTEND_ORIGINS": ["http://localhost:5173"], "GROQ_API_KEY": None, "GROQ_MODEL": "openai/gpt-oss-20b", "AI_MOCK_MODE": False}
    config.update(extra_config or {})
    app = create_app(config)
    return app.test_client(), database, app


def register(client, email="student@university.edu", **extra):
    return client.post("/api/auth/register", json={"name": "Student One", "email": email, "password": "safe-password-123", **extra})


def auth(token): return {"Authorization": f"Bearer {token}"}


def test_configured_mongodb_failure_leaves_degraded_health(monkeypatch):
    import app.extensions as extensions
    class UnavailableMongo:
        def __init__(self, *_args, **_kwargs): self.admin = self
        def command(self, *_args, **_kwargs): raise TimeoutError("connection unavailable")
        def close(self): pass
    monkeypatch.setattr(extensions, "MongoClient", UnavailableMongo)
    app = create_app({"TESTING": False, "SECRET_KEY": "test-secret-key-long-enough-for-tests", "MONGODB_URI": "mongodb://unavailable", "FRONTEND_ORIGINS": []})
    response = app.test_client().get("/api/health")
    assert response.status_code == 503 and response.json["database"] == "unavailable"


def test_groq_forbidden_is_not_retried_and_is_explained(monkeypatch):
    from flask import Flask
    from app.agents import groq
    calls = []
    class Forbidden(Exception): code = 403
    def fake_completion(*_args, **_kwargs):
        calls.append(1)
        raise Forbidden()
    monkeypatch.setattr(groq, "_groq_completion", fake_completion)
    app = Flask(__name__)
    app.config.update(GROQ_API_KEY="mock-key", GROQ_MODEL="openai/gpt-oss-20b")
    with app.app_context(), pytest.raises(RuntimeError, match="HTTP 403"):
        groq.generate_json("prompt", {}, retries=2)
    assert len(calls) == 1


def test_agent_specific_model_key_timeout_tokens_and_usage(monkeypatch):
    from types import SimpleNamespace
    from flask import Flask
    from app.agents import groq
    captured = {}
    def fake_completion(api_key, model, messages, timeout_ms, max_output_tokens):
        captured.update(api_key=api_key, model=model, messages=messages, timeout_ms=timeout_ms, max_output_tokens=max_output_tokens)
        return {"model": model, "choices": [{"message": {"content": '{"problemStatement":"A clear problem.","technicalFeasibility":"Feasible.","complexity":"Low","requiredResources":[],"timeEstimateWeeks":4,"expectedDifficulty":"Low","challenges":[],"assumptions":[]}'}}], "usage": {"prompt_tokens": 120, "completion_tokens": 80, "total_tokens": 200}}
    monkeypatch.setattr(groq, "_groq_completion", fake_completion)
    app = Flask(__name__)
    app.config.update(AGENT_FEASIBILITY_API_KEY="agent-key", GROQ_API_KEY="shared-key", AGENT_FEASIBILITY_MODEL="agent-model", AGENT_FEASIBILITY_TIMEOUT_MS=17000, AGENT_FEASIBILITY_MAX_OUTPUT_TOKENS=512, AGENT_FEASIBILITY_INPUT_COST_PER_MILLION=1.0, AGENT_FEASIBILITY_OUTPUT_COST_PER_MILLION=2.0)
    with app.app_context():
        result, metrics = groq.generate_agent_json("feasibility", "prompt", {}, 300)
    assert result["complexity"] == "Low"
    assert captured["api_key"] == "agent-key"
    assert captured["timeout_ms"] == 17000
    assert captured["model"] == "agent-model"
    assert captured["max_output_tokens"] == 300
    assert (metrics["inputTokens"], metrics["outputTokens"], metrics["totalTokens"]) == (120, 80, 200)
    assert metrics["estimatedCostUsd"] == 0.00028


def test_registration_hashes_password_issues_jwt_and_prevents_duplicates():
    api, database, app = client()
    response = register(api)
    assert response.status_code == 201
    user = response.json["user"]
    saved = database.users.find_one({"email": user["email"]})
    assert saved["passwordHash"] != "safe-password-123"
    assert bcrypt.checkpw(b"safe-password-123", saved["passwordHash"].encode())
    assert "passwordHash" not in user
    claims = jwt.decode(response.json["token"], app.config["SECRET_KEY"], algorithms=["HS256"])
    assert claims["sub"] == user["uid"]
    assert register(api).status_code == 409


def test_registration_defaults_to_student_and_faculty_request_needs_admin_approval():
    api, database, _ = client()
    assert api.post("/api/auth/register", json={"name": "Self Faculty", "email": "self-faculty@university.edu", "password": "safe-password-123", "role": "faculty"}).status_code == 400
    assert api.post("/api/auth/register", json={"name": "Self Admin", "email": "self-admin@university.edu", "password": "safe-password-123", "role": "admin"}).status_code == 400
    applied = register(api, "applicant@university.edu", requestFacultyAccess=True)
    assert applied.status_code == 201
    assert applied.json["user"]["role"] == "student"
    assert applied.json["user"]["facultyAccessRequestStatus"] == "PENDING"
    assert database.facultyAccessRequests.find_one({"userId": applied.json["user"]["uid"], "status": "PENDING"})
    headers = auth(applied.json["token"])
    assert api.post("/api/auth/faculty-access-request", headers=headers).status_code == 409
    assert api.get("/api/admin/faculty-requests", headers=headers).status_code == 403


def test_admin_approves_or_rejects_faculty_requests_and_blocks_self_role_changes():
    api, database, _ = client()
    admin = register(api, "admin-approver@university.edu").json
    from bson import ObjectId
    admin_id = admin["user"]["uid"]
    database.users.update_one({"_id": ObjectId(admin_id)}, {"$set": {"role": "admin"}})
    admin_headers = auth(admin["token"])
    applicant = register(api, "approve-me@university.edu", requestFacultyAccess=True).json
    request_doc = database.facultyAccessRequests.find_one({"userId": applicant["user"]["uid"]})
    assert api.post(f"/api/admin/faculty-requests/{request_doc['_id']}/review", headers=admin_headers, json={"decision": "APPROVED"}).status_code == 200
    approved = database.users.find_one({"_id": ObjectId(applicant["user"]["uid"])})
    assert approved["role"] == "faculty" and approved["facultyAccessRequestStatus"] == "APPROVED"
    assert api.post(f"/api/admin/faculty-requests/{request_doc['_id']}/review", headers=admin_headers, json={"decision": "REJECTED"}).status_code == 409
    assert api.patch(f"/api/admin/users/{admin_id}/role", headers=admin_headers, json={"role": "student"}).status_code == 403
    assert api.patch(f"/api/admin/users/{applicant['user']['uid']}/role", headers=admin_headers, json={"role": "faculty"}).status_code == 409
    extra_admin = register(api, "new-admin@university.edu").json
    assert api.patch(f"/api/admin/users/{extra_admin['user']['uid']}/role", headers=admin_headers, json={"role": "admin"}).status_code == 200
    assert database.users.find_one({"_id": ObjectId(extra_admin["user"]["uid"])})["role"] == "admin"

    rejected_applicant = register(api, "reject-me@university.edu", requestFacultyAccess=True).json
    rejected_doc = database.facultyAccessRequests.find_one({"userId": rejected_applicant["user"]["uid"]})
    response = api.post(f"/api/admin/faculty-requests/{rejected_doc['_id']}/review", headers=admin_headers, json={"decision": "REJECTED"})
    assert response.status_code == 200
    rejected_user = database.users.find_one({"_id": ObjectId(rejected_applicant["user"]["uid"])})
    assert rejected_user["role"] == "student" and rejected_user["facultyAccessRequestStatus"] == "REJECTED"


def test_first_admin_bootstrap_is_one_time_and_hashes_password():
    import bcrypt as bcrypt_lib
    from mongomock import MongoClient
    from create_admin import create_first_admin
    database = MongoClient().testdb
    first_id = create_first_admin(database, "root@university.edu", "First Admin", "long-safe-password-123")
    saved = database.users.find_one({"_id": __import__("bson").ObjectId(first_id)})
    assert saved["role"] == "admin" and bcrypt_lib.checkpw(b"long-safe-password-123", saved["passwordHash"].encode())
    with pytest.raises(RuntimeError, match="already exists"):
        create_first_admin(database, "second@university.edu", "Second Admin", "another-long-password")


def test_profile_saves_programming_languages_and_previous_project_experience():
    api, _, _ = client()
    student = register(api).json
    response = api.put("/api/profile", headers=auth(student["token"]), json={"department": "Computing", "year": 2, "skills": [{"name": "Python", "level": "Intermediate"}], "programmingLanguages": ["Python", "JavaScript"], "previousProjectExperience": "Built a campus events site."})
    assert response.status_code == 200
    assert response.json["profile"]["programmingLanguages"] == ["Python", "JavaScript"]
    assert response.json["profile"]["previousProjectExperience"] == "Built a campus events site."


def test_login_role_from_database_and_jwt_protection():
    api, database, app = client()
    registered = register(api).json
    response = api.post("/api/auth/login", json={"email": "student@university.edu", "password": "safe-password-123"})
    assert response.status_code == 200
    token = response.json["token"]
    assert api.get("/api/auth/me", headers=auth(token)).json["user"]["role"] == "student"
    assert api.get("/api/admin/users", headers=auth(token)).status_code == 403
    assert api.get("/api/profile").status_code == 401
    expired = jwt.encode({"sub": registered["user"]["uid"], "exp": datetime.now(timezone.utc) - timedelta(seconds=10)}, app.config["SECRET_KEY"], algorithm="HS256")
    assert api.get("/api/auth/me", headers=auth(expired)).status_code == 401
    assert api.get("/api/auth/me", headers=auth("not-a-jwt")).status_code == 401
    assert api.post("/api/auth/login", json={"email": "student@university.edu", "password": "incorrect"}).status_code == 401


def test_admin_role_and_project_access():
    api, database, _ = client()
    admin = register(api, "admin@university.edu").json
    assert admin["user"]["role"] == "student"
    from bson import ObjectId
    database.users.update_one({"_id": ObjectId(admin["user"]["uid"])}, {"$set": {"role": "admin"}})
    admin_headers = auth(admin["token"])
    assert api.get("/api/admin/users", headers=admin_headers).status_code == 200
    assert all("passwordHash" not in item for item in api.get("/api/admin/users", headers=auth(admin["token"])).json["users"])
    student = register(api, "s@university.edu").json
    headers = auth(student["token"])
    created = api.post("/api/projects", headers=headers, json={"title": "Campus map", "idea": "A map that improves access around the university."})
    assert created.status_code == 201
    project = created.json["project"]
    assert len(project["id"]) == 24
    assert api.get(f"/api/projects/{project['id']}", headers=headers).status_code == 200
    assert api.get("/api/projects", headers=admin_headers).status_code == 200
    assert api.post(f"/api/projects/{project['id']}/chat", headers=admin_headers, json={"message": "Access check"}).status_code == 403
    assert database.projects.find_one({"_id": __import__("bson").ObjectId(project["id"])}) is not None


def test_planning_pipeline_uses_mocked_ai_and_persists_results(monkeypatch):
    from app.agents import groq
    monkeypatch.setattr(groq, "generate_agent_json", lambda agent, *_args, **_kwargs: (groq.mock_agent_result(agent), {"model": "fixture-model", "status": "completed", "mode": "mock", "requestCount": 1, "latencyMs": 33, "inputTokens": 12, "outputTokens": 8, "totalTokens": 20, "estimatedCostUsd": 0.0001, "usageAvailable": True}))
    api, database, _ = client()
    student = register(api).json
    headers = auth(student["token"])
    project = api.post("/api/projects", headers=headers, json={"title": "Campus map", "idea": "A map that improves access around campus."}).json["project"]
    plan = api.post(f"/api/projects/{project['id']}/plan", headers=headers)
    assert plan.status_code == 200
    assert api.get(f"/api/projects/{project['id']}/plan-history", headers=headers).json["history"] == []
    assert len(list(database.agentResults.find({"projectId": project["id"]}))) == 5
    milestones = list(database.milestones.find({"projectId": project["id"]}))
    assert len(milestones) == 4
    milestone = milestones[0]
    updated = api.patch(f"/api/projects/{project['id']}/milestones/{milestone['_id']}", headers=headers, json={"status": "In Progress", "progress": 25, "description": "Initial reading complete."})
    assert updated.status_code == 200
    saved_plan = database.milestones.find_one({"_id": milestone["_id"]})
    assert saved_plan["tasks"] == ["Confirm scope"] and saved_plan["status"] == "In Progress"
    progress = api.post(f"/api/projects/{project['id']}/progress", headers=headers, json={"summary": "Completed initial research", "completedTasks": ["Read documentation"], "challenges": "None"})
    assert progress.status_code == 201
    assert api.post(f"/api/projects/{project['id']}/plan", headers=headers).status_code == 409
    replacement = api.post(f"/api/projects/{project['id']}/plan", headers=headers, json={"confirmReplace": True})
    assert replacement.status_code == 200, replacement.json
    archived = api.get(f"/api/projects/{project['id']}/plan-history", headers=headers).json["history"]
    assert len(archived) == 1 and len(archived[0]["milestones"]) == 4
    usage = api.get(f"/api/projects/{project['id']}/ai-usage", headers=headers).json["usage"]
    assert usage["requests"] == 10 and usage["totalTokens"] == 200 and usage["estimatedCostUsd"] == 0.001
    from app.routes import mentor
    monkeypatch.setattr(mentor, "generate_json", lambda *_args, **_kwargs: {"answer": "Start by drafting a small prototype.", "suggestedNextSteps": ["Outline the prototype"]})
    chat = api.post(f"/api/projects/{project['id']}/chat", headers=headers, json={"message": "What next?"})
    assert chat.status_code == 200
    assert len(list(database.mentorChats.find({"projectId": project["id"]}))) == 2
    from app.routes import risks
    assert len(api.get(f"/api/projects/{project['id']}/risks", headers=headers).json["risks"]) == 1
    monkeypatch.setattr(risks, "generate_json", lambda *_args, **_kwargs: {"summary": "The research phase is progressing.", "risks": [{"category": "Access", "description": "Dataset access may be delayed.", "severity": "Medium", "probability": "Medium", "mitigation": "Request access early."}]})
    assessment = api.post(f"/api/projects/{project['id']}/risks/assess", headers=headers)
    assert assessment.status_code == 201
    assert database.riskAssessments.find_one({"projectId": project["id"]})["risks"][0]["category"] == "Access"


def test_faculty_only_sees_assigned_projects_and_admin_can_assign(monkeypatch):
    from app.agents import groq
    api, database, _ = client()
    admin = register(api, "admin@university.edu").json
    from bson import ObjectId
    database.users.update_one({"_id": ObjectId(admin["user"]["uid"])}, {"$set": {"role": "admin"}})
    headers = auth(admin["token"])
    faculty = register(api, "faculty@university.edu", requestFacultyAccess=True).json
    student = register(api, "one@university.edu").json
    other = register(api, "two@university.edu").json
    faculty_request = database.facultyAccessRequests.find_one({"userId": faculty["user"]["uid"]})
    assert api.post(f"/api/admin/faculty-requests/{faculty_request['_id']}/review", headers=headers, json={"decision": "APPROVED"}).status_code == 200
    project_one = api.post("/api/projects", headers=auth(student["token"]), json={"title": "Assigned", "idea": "A research project that belongs to the assigned student."}).json["project"]
    project_two = api.post("/api/projects", headers=auth(other["token"]), json={"title": "Private", "idea": "A different project owned by another student."}).json["project"]
    assert api.post("/api/admin/assignments", headers=headers, json={"facultyId": faculty["user"]["uid"], "projectId": project_one["id"]}).status_code == 201
    faculty_headers = auth(faculty["token"])
    ai_calls = []
    monkeypatch.setattr(groq, "generate_json", lambda *_args, **_kwargs: (ai_calls.append(1) or {"summary": "A concise summary based on the stored project."}))
    faculty_detail = api.get(f"/api/faculty/projects/{project_one['id']}", headers=faculty_headers)
    assert faculty_detail.status_code == 200 and not ai_calls
    summary = api.post(f"/api/faculty/projects/{project_one['id']}/summary", headers=faculty_headers)
    assert summary.status_code == 200 and ai_calls
    assert api.get(f"/api/faculty/projects/{project_two['id']}", headers=faculty_headers).status_code == 403
    assert api.get("/api/faculty/dashboard", headers=faculty_headers).json["summary"]["assignedProjects"] == 1
    overview = api.get("/api/admin/overview", headers=headers).json["overview"]
    assert overview["totalProjects"] == 2 and overview["faculty"] == 1
    assignments = api.get("/api/admin/assignments", headers=headers).json["assignments"]
    assert len(assignments) == 1 and assignments[0]["project"] == "Assigned"
    assert api.delete(f"/api/admin/assignments/{assignments[0]['id']}", headers=headers).status_code == 200


def test_planning_retry_preserves_completed_agents_and_retries_downstream_only(monkeypatch):
    from app.agents import groq
    calls = []
    failed_once = {"technology": False}
    def generate(agent, _prompt, _payload, _output_limit=None):
        calls.append(agent)
        if agent == "technology" and not failed_once[agent]:
            failed_once[agent] = True
            raise groq.AgentRunError(agent, "mock failure", {"model": "mock", "status": "failed", "requestCount": 0, "latencyMs": 0, "inputTokens": None, "outputTokens": None, "totalTokens": None, "estimatedCostUsd": None})
        return groq.mock_agent_result(agent), {"model": "mock", "status": "mock", "requestCount": 0, "latencyMs": 0, "inputTokens": None, "outputTokens": None, "totalTokens": None, "estimatedCostUsd": None, "usageAvailable": False}
    monkeypatch.setattr(groq, "generate_agent_json", generate)
    api, database, _ = client()
    student = register(api).json
    headers = auth(student["token"])
    project = api.post("/api/projects", headers=headers, json={"title": "Sample", "idea": "A small academic project with a clear use case."}).json["project"]
    first = api.post(f"/api/projects/{project['id']}/plan", headers=headers)
    assert first.status_code == 503 and first.json["failedAgent"] == "technology"
    assert first.json["completedAgents"] == ["feasibility", "scope"]
    assert calls == ["feasibility", "scope", "technology"]
    records = list(database.agentResults.find({"projectId": project["id"]}))
    assert [item["status"] for item in records].count("completed") == 2
    retry = api.post(f"/api/projects/{project['id']}/plan/retry", headers=headers)
    assert retry.status_code == 200
    assert calls == ["feasibility", "scope", "technology", "technology", "milestones", "risks"]
    project_doc = database.projects.find_one({"ownerId": student["user"]["uid"]})
    run_id = project_doc["planRunId"]
    assert len(list(database.agentResults.find({"projectId": project["id"], "runId": run_id}))) == 6
    assert api.get(f"/api/projects/{project['id']}/ai-usage", headers=headers).json["usage"]["requests"] == 0


def test_ai_mock_mode_runs_blueprint_without_calling_groq(monkeypatch):
    from app.agents import groq
    monkeypatch.setattr(groq, "_groq_completion", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("Groq must not be called in mock mode")))
    api, database, _ = client({"AI_MOCK_MODE": True})
    student = register(api).json
    headers = auth(student["token"])
    project = api.post("/api/projects", headers=headers, json={"title": "Mocked", "idea": "A small project used to verify mock planning."}).json["project"]
    response = api.post(f"/api/projects/{project['id']}/plan", headers=headers)
    assert response.status_code == 200
    assert len(list(database.agentResults.find({"projectId": project["id"], "status": "completed"}))) == 5
    assert api.get(f"/api/projects/{project['id']}/ai-usage", headers=headers).json["usage"]["requests"] == 0


def test_document_metadata_and_local_storage_without_cloudinary(monkeypatch, tmp_path):
    from app.routes import documents
    monkeypatch.setattr(documents, "generate_json", lambda *_args, **_kwargs: {"title": "Synopsis", "content": "Draft based on stored facts."})
    api, database, _ = client({"LOCAL_UPLOAD_DIR": str(tmp_path)})
    student = register(api).json
    headers = auth(student["token"])
    project = api.post("/api/projects", headers=headers, json={"title": "Campus map", "idea": "A map that improves access around the university."}).json["project"]
    response = api.post(f"/api/projects/{project['id']}/documents", headers=headers, json={"type": "synopsis"})
    assert response.status_code == 201
    document = response.json["document"]
    saved = database.generatedDocuments.find_one({"projectId": project["id"]})
    assert saved["storageProvider"] == "local" and "storagePath" not in document
    link = api.get(f"/api/projects/{project['id']}/documents/{document['id']}/download", headers=headers).json["downloadUrl"]
    file_response = api.get(link, headers=headers)
    assert file_response.status_code == 200 and b"Draft based" in file_response.data
    upload = api.post(f"/api/projects/{project['id']}/files", headers=headers, data={"file": (BytesIO(b"Supporting notes"), "notes.txt")}, content_type="multipart/form-data")
    assert upload.status_code == 201
    uploaded_id = upload.json["document"]["id"]
    assert api.delete(f"/api/projects/{project['id']}/documents/{uploaded_id}", headers=headers).status_code == 200
    assert api.post(f"/api/projects/{project['id']}/files", headers=headers, data={"file": (BytesIO(b"no"), "bad.exe")}, content_type="multipart/form-data").status_code == 400
