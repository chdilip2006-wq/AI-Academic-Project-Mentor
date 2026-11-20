from datetime import datetime, timezone
from ..extensions import db
from .store import now


def refresh_project_health(project_id):
    project_ref = db.collection("projects").document(project_id)
    project_snap = project_ref.get()
    if not project_snap.exists:
        return None
    project = project_snap.to_dict() or {}
    milestones = [item.to_dict() or {} for item in db.collection("milestones").where("projectId", "==", project_id).stream()]
    reports = [item.to_dict() or {} for item in db.collection("progressUpdates").where("projectId", "==", project_id).stream()]
    assessments = [item.to_dict() or {} for item in db.collection("riskAssessments").where("projectId", "==", project_id).stream()]
    percentages = [max(0, min(100, int(milestone.get("progress", 0) or 0))) for milestone in milestones]
    overall = round(sum(percentages) / len(percentages)) if percentages else int(project.get("overallProgress", 0) or 0)
    completed = bool(milestones) and all(item.get("status") == "Completed" for item in milestones)
    overdue = False
    upcoming = False
    today = datetime.now(timezone.utc).date()
    for milestone in milestones:
        due = milestone.get("dueDate")
        if not due or milestone.get("status") == "Completed":
            continue
        try:
            due_date = datetime.fromisoformat(str(due).replace("Z", "+00:00")).date()
            if due_date < today:
                overdue = True
            elif (due_date - today).days <= 7:
                upcoming = True
        except ValueError:
            continue
    all_risks = list((project.get("blueprint") or {}).get("risks", {}).get("risks", []))
    all_risks.extend(item for assessment in assessments for item in assessment.get("risks", []))
    serious_reported_risk = any(
        item.get("severity") == "High" and item.get("probability") == "High"
        for item in all_risks if isinstance(item, dict)
    )
    no_issue_values = {"none", "no", "n/a", "na", "no blockers", "no challenges"}
    reported_challenge = any(isinstance(item.get("challenges"), str) and item["challenges"].strip().lower() not in no_issue_values for item in reports)
    delayed = overdue or any(item.get("status") == "Delayed" for item in milestones)
    if completed or (milestones and overall == 100):
        health = "Completed"
    elif delayed or serious_reported_risk:
        health = "At Risk"
    elif reported_challenge or upcoming:
        health = "Needs Attention"
    else:
        health = "On Track"
    changes = {"health": health, "overallProgress": overall, "updatedAt": now()}
    project_ref.update(changes)
    return changes
