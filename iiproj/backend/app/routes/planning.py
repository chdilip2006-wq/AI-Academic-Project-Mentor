from datetime import timedelta
from functools import wraps
from uuid import uuid4
from flask import Blueprint, current_app, g, jsonify, request
from pymongo.errors import DuplicateKeyError
from ..extensions import db
from ..middleware.auth import require_auth
from ..middleware.rate_limit import rate_limit
from ..services.store import now, project_for_user, serialize
from ..agents.groq import AGENT_NAMES, AgentRunError, _latest_for_agent, generate_json, friendly_failure, planning_lock, run_planning

bp = Blueprint("planning", __name__)


def serialized_project_run(view):
    @wraps(view)
    def wrapped(project_id, *args, **kwargs):
        project_for_user(project_id, g.user, write=True)
        with planning_lock(project_id):
            lock_document = db.collection("planningLocks").document(project_id)
            raw = db.collection("planningLocks").collection
            ttl = int(current_app.config.get("AI_PLANNING_LOCK_TTL_SECONDS", 1200))
            raw.find_one_and_delete({"_id": lock_document._doc_id, "createdAt": {"$lt": now() - timedelta(seconds=ttl)}})
            request_lock_id = uuid4().hex
            try:
                raw.insert_one({"_id": lock_document._doc_id, "runId": request_lock_id, "createdAt": now()})
            except DuplicateKeyError:
                return jsonify({"error": "Blueprint generation is already running for this project."}), 409
            try:
                return view(project_id, *args, **kwargs)
            finally:
                raw.delete_one({"_id": lock_document._doc_id, "runId": request_lock_id})
    return wrapped


def _latest_records(project_id, run_id):
    records = [item.to_dict() or {} for item in db.collection("agentResults").where("projectId", "==", project_id).where("runId", "==", run_id).stream()]
    return {name: _latest_for_agent(records, name) for name in AGENT_NAMES}


def _finish_plan(ref, project_id, project, results, blueprint):
    generated_at = now()
    blueprint["generatedAt"] = generated_at
    if project.get("blueprint"):
        prior_milestones = [serialize(item) for item in db.collection("milestones").where("projectId", "==", project_id).stream()]
        db.collection("blueprintHistory").document().set({"projectId": project_id, "ownerId": project["ownerId"], "blueprint": project["blueprint"], "milestones": prior_milestones, "archivedAt": generated_at})
        for old_milestone in db.collection("milestones").where("projectId", "==", project_id).stream():
            db.collection("milestones").document(old_milestone.id).delete()
    for index, milestone in enumerate(blueprint.get("planning", {}).get("milestones", [])):
        db.collection("milestones").document().set({**milestone, "projectId": project_id, "ownerId": project["ownerId"], "status": "Not Started", "progress": 0, "order": index + 1, "createdAt": generated_at, "updatedAt": generated_at})
    ref.update({"blueprint": blueprint, "planningStatus": "completed", "failedAgent": None, "planningError": None, "status": "planned", "updatedAt": generated_at})
    return jsonify({"blueprint": blueprint, "agentResults": results})


def _run_and_respond(ref, project_id, project, profile, run_id, start_index):
    ref.update({"planningStatus": "generating", "planningError": None, "updatedAt": now()})
    try:
        results, blueprint = run_planning(project_id, run_id, project, profile, start_index)
        return _finish_plan(ref, project_id, project, results, blueprint)
    except AgentRunError as error:
        ref.update({"planningStatus": "partial", "failedAgent": error.agent, "planningError": str(error)[:300], "updatedAt": now()})
        completed = [name for name, record in _latest_records(project_id, run_id).items() if record and record.get("status") == "completed"]
        return jsonify({"error": str(error), "failedAgent": error.agent, "completedAgents": completed, "retryEndpoint": f"/api/projects/{project_id}/plan/retry"}), 503
    except Exception as error:
        ref.update({"planningStatus": "partial", "planningError": str(error)[:300], "updatedAt": now()})
        return jsonify({"error": "Blueprint processing failed after partial progress. Retry the incomplete agent from the project workspace."}), 503


@bp.post("/projects/<project_id>/plan")
@rate_limit(5, 600)
@require_auth("student")
@serialized_project_run
def generate_plan(project_id):
    ref, project = project_for_user(project_id, g.user, write=True)
    data = request.get_json(silent=True) or {}
    if project.get("planningStatus") == "generating":
        return jsonify({"error": "Blueprint generation is already running for this project."}), 409
    if project.get("planningStatus") == "partial" and project.get("planRunId") and not project.get("blueprint"):
        return jsonify({"error": "A partial run is saved. Resume it with the retry action to preserve completed agents."}), 409
    if project.get("blueprint") and data.get("confirmReplace") is not True:
        return jsonify({"error": "A blueprint already exists. Confirm replacement before generating a new plan."}), 409
    profile_doc = db.collection("studentProfiles").document(g.user["uid"]).get()
    profile = profile_doc.to_dict() if profile_doc.exists else {}
    run_id = uuid4().hex
    ref.update({"planRunId": run_id, "planningStatus": "generating", "failedAgent": None, "updatedAt": now()})
    return _run_and_respond(ref, project_id, project, profile, run_id, 0)


@bp.post("/projects/<project_id>/plan/retry")
@rate_limit(5, 600)
@require_auth("student")
@serialized_project_run
def retry_plan(project_id):
    ref, project = project_for_user(project_id, g.user, write=True)
    if project.get("planningStatus") == "generating":
        return jsonify({"error": "Blueprint generation is already running for this project."}), 409
    run_id = project.get("planRunId")
    if not run_id or project.get("planningStatus") != "partial":
        return jsonify({"error": "There is no incomplete blueprint run to resume."}), 409
    latest = _latest_records(project_id, run_id)
    start_index = next((index for index, name in enumerate(AGENT_NAMES) if not latest.get(name) or latest[name].get("status") != "completed"), len(AGENT_NAMES))
    profile_doc = db.collection("studentProfiles").document(g.user["uid"]).get()
    profile = profile_doc.to_dict() if profile_doc.exists else {}
    return _run_and_respond(ref, project_id, project, profile, run_id, start_index)


@bp.get("/projects/<project_id>/ai-usage")
@require_auth("student", "faculty", "admin")
def ai_usage(project_id):
    project_for_user(project_id, g.user)
    records = [item.to_dict() or {} for item in db.collection("agentResults").where("projectId", "==", project_id).stream()]
    total = lambda key: sum(int(item.get(key, 0) or 0) for item in records)
    estimated = [float(item["estimatedCostUsd"]) for item in records if item.get("estimatedCostUsd") is not None]
    latest = {}
    for record in records:
        name = record.get("agent")
        if name and (name not in latest or int(record.get("sequence", 0) or 0) > int(latest[name].get("sequence", 0) or 0)):
            latest[name] = record
    return jsonify({"usage": {
        "requests": total("requestCount"), "inputTokens": total("inputTokens"),
        "outputTokens": total("outputTokens"), "totalTokens": total("totalTokens"),
        "estimatedCostUsd": round(sum(estimated), 8) if estimated else None,
        "costEstimatesAvailable": bool(estimated),
        "requestLimit": current_app.config.get("AI_MAX_AGENT_REQUESTS_PER_PROJECT", 25),
        "tokenLimit": current_app.config.get("AI_MAX_TOKENS_PER_PROJECT", 100000),
        "agents": [{"agent": name, "model": latest.get(name, {}).get("model"), "mode": latest.get(name, {}).get("mode"), "status": latest.get(name, {}).get("status"), "latencyMs": latest.get(name, {}).get("latencyMs"), "attempts": sum(1 for row in records if row.get("agent") == name), "requests": sum(int(row.get("requestCount", 0) or 0) for row in records if row.get("agent") == name), "inputTokens": sum(int(row.get("inputTokens", 0) or 0) for row in records if row.get("agent") == name), "outputTokens": sum(int(row.get("outputTokens", 0) or 0) for row in records if row.get("agent") == name), "totalTokens": sum(int(row.get("totalTokens", 0) or 0) for row in records if row.get("agent") == name), "estimatedCostUsd": round(sum(float(row["estimatedCostUsd"]) for row in records if row.get("agent") == name and row.get("estimatedCostUsd") is not None), 8) if any(row.get("agent") == name and row.get("estimatedCostUsd") is not None for row in records) else None} for name in AGENT_NAMES],
    }})


@bp.get("/projects/<project_id>/plan-history")
@require_auth("student", "faculty", "admin")
def plan_history(project_id):
    project_for_user(project_id, g.user)
    docs = db.collection("blueprintHistory").where("projectId", "==", project_id).stream()
    history = [serialize(item) for item in docs]
    return jsonify({"history": sorted(history, key=lambda item: item.get("archivedAt", ""), reverse=True)})


@bp.post("/projects/<project_id>/plan-adjustments")
@rate_limit(10, 3600)
@require_auth("student")
def suggest_plan_adjustment(project_id):
    _, project = project_for_user(project_id, g.user, write=True)
    updates = list(db.collection("progressUpdates").where("projectId", "==", project_id).stream())
    try:
        suggestion = generate_json("You are an academic planning mentor. Analyze the current plan and progress. Suggest adjustments to future milestones without changing past work. Return JSON with keys summary, proposedChanges (array of objects with milestoneOrder, reason, suggestedTasks, revisedDeliverables), tradeoffs.", {"blueprint": project.get("blueprint"), "progressUpdates": [u.to_dict() for u in updates]})
    except Exception as error:
        return jsonify({"error": friendly_failure(error, "plan adjustment service")}), 503
    if not isinstance(suggestion, dict) or not isinstance(suggestion.get("summary"), str) or not isinstance(suggestion.get("proposedChanges"), list):
        return jsonify({"error": "The plan adjustment agent returned an invalid response. Please retry."}), 502
    ref = db.collection("planSuggestions").document()
    ref.set({"projectId": project_id, "ownerId": g.user["uid"], "suggestion": suggestion, "status": "pending", "createdAt": now()})
    return jsonify({"suggestion": {**suggestion, "id": ref.id}}), 201


@bp.post("/projects/<project_id>/plan-adjustments/<suggestion_id>/apply")
@require_auth("student")
def apply_plan_adjustment(project_id, suggestion_id):
    project_for_user(project_id, g.user, write=True)
    suggestion_ref = db.collection("planSuggestions").document(suggestion_id)
    snap = suggestion_ref.get()
    if not snap.exists or snap.to_dict().get("projectId") != project_id:
        return jsonify({"error": "Plan suggestion not found."}), 404
    body = __import__("flask").request.get_json(silent=True) or {}
    if body.get("confirm") is not True:
        return jsonify({"error": "Confirm the changes before applying."}), 400
    suggestion_data = snap.to_dict().get("suggestion", {})
    applied = []
    for change in suggestion_data.get("proposedChanges", []):
        try:
            order = int(change.get("milestoneOrder"))
        except (ValueError, TypeError, AttributeError):
            continue
        milestone_docs = db.collection("milestones").where("projectId", "==", project_id).where("order", "==", order).limit(1).stream()
        milestone = next(iter(milestone_docs), None)
        if not milestone or milestone.to_dict().get("status") == "Completed":
            continue
        milestone_ref = db.collection("milestones").document(milestone.id)
        updates = {"updatedAt": now(), "lastPlanSuggestionId": suggestion_id}
        if isinstance(change.get("suggestedTasks"), list):
            updates["tasks"] = change["suggestedTasks"]
        if isinstance(change.get("revisedDeliverables"), list):
            updates["deliverables"] = change["revisedDeliverables"]
        milestone_ref.update(updates)
        applied.append(order)
    suggestion_ref.update({"status": "accepted", "acceptedAt": now(), "appliedMilestones": applied})
    return jsonify({"message": "The confirmed plan changes were applied to remaining milestones.", "appliedMilestones": applied, "suggestion": suggestion_data})
