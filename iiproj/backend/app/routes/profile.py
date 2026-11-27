from flask import Blueprint, g, jsonify, request
from ..extensions import db
from ..middleware.auth import require_auth
from ..services.store import now
from ..utils.validation import json_body, required_text

bp = Blueprint("profile", __name__)

ASSESSMENT_QUESTIONS = [
    {"id": "programming_1", "domain": "Programming fundamentals", "prompt": "A loop should process every item in a list once. Which approach avoids an off-by-one error?", "options": [{"id": "a", "text": "Iterate from index 0 while the index is less than the list length"}, {"id": "b", "text": "Iterate from index 0 while the index is less than or equal to the list length"}, {"id": "c", "text": "Start at index 1 and stop before the list length"}, {"id": "d", "text": "Use a loop that never checks the list length"}], "answer": "a"},
    {"id": "programming_2", "domain": "Programming fundamentals", "prompt": "A function receives a number and should return whether it is even. Which condition is correct?", "options": [{"id": "a", "text": "number / 2 == 0"}, {"id": "b", "text": "number % 2 == 0"}, {"id": "c", "text": "number * 2 == 0"}, {"id": "d", "text": "number + 2 == 0"}], "answer": "b"},
    {"id": "web_1", "domain": "Web and APIs", "prompt": "A browser submits a new project to a REST API. Which HTTP method is the usual choice for creating it?", "options": [{"id": "a", "text": "GET"}, {"id": "b", "text": "POST"}, {"id": "c", "text": "DELETE"}, {"id": "d", "text": "OPTIONS"}], "answer": "b"},
    {"id": "web_2", "domain": "Web and APIs", "prompt": "An API successfully created a new resource. Which status code most specifically communicates that?", "options": [{"id": "a", "text": "200 OK"}, {"id": "b", "text": "201 Created"}, {"id": "c", "text": "401 Unauthorized"}, {"id": "d", "text": "404 Not Found"}], "answer": "b"},
    {"id": "database_1", "domain": "Databases", "prompt": "You need each account email to be unique. Which database feature best enforces that rule?", "options": [{"id": "a", "text": "A unique constraint or unique index"}, {"id": "b", "text": "Sorting the account list"}, {"id": "c", "text": "A longer email field"}, {"id": "d", "text": "A comment in the code"}], "answer": "a"},
    {"id": "database_2", "domain": "Databases", "prompt": "Which query operation is used to retrieve only records that match a condition?", "options": [{"id": "a", "text": "Filter / WHERE"}, {"id": "b", "text": "INSERT"}, {"id": "c", "text": "DROP"}, {"id": "d", "text": "COMMIT only"}], "answer": "a"},
    {"id": "data_ai_1", "domain": "Data and AI", "prompt": "A model performs very well on training examples but poorly on new examples. What is the most likely issue?", "options": [{"id": "a", "text": "Overfitting"}, {"id": "b", "text": "The model has no input data"}, {"id": "c", "text": "The test set was used as the training set"}, {"id": "d", "text": "The output is always deterministic"}], "answer": "a"},
    {"id": "data_ai_2", "domain": "Data and AI", "prompt": "Why should data be split into training and test sets when evaluating a predictive model?", "options": [{"id": "a", "text": "To check performance on examples not used to fit the model"}, {"id": "b", "text": "To make every model use the same algorithm"}, {"id": "c", "text": "To remove the need to inspect data quality"}, {"id": "d", "text": "To guarantee perfect predictions"}], "answer": "a"},
    {"id": "testing_1", "domain": "Debugging and testing", "prompt": "A function fails only for an empty list. What is the most useful first test to add?", "options": [{"id": "a", "text": "A focused test that calls the function with an empty list and checks expected behavior"}, {"id": "b", "text": "A test that uses only a very large list"}, {"id": "c", "text": "A test that skips the function"}, {"id": "d", "text": "A test that checks an unrelated screen"}], "answer": "a"},
    {"id": "testing_2", "domain": "Debugging and testing", "prompt": "A bug report says a form fails after a particular sequence of actions. What should you do first?", "options": [{"id": "a", "text": "Reproduce the steps and inspect the relevant error or state"}, {"id": "b", "text": "Rewrite the entire application"}, {"id": "c", "text": "Delete the report"}, {"id": "d", "text": "Assume the issue fixed itself"}], "answer": "a"},
    {"id": "version_control_1", "domain": "Version control", "prompt": "What is the main purpose of a Git commit?", "options": [{"id": "a", "text": "Save a named snapshot of changes in project history"}, {"id": "b", "text": "Deploy the application automatically in every setup"}, {"id": "c", "text": "Replace the need for backups and testing"}, {"id": "d", "text": "Install project dependencies"}], "answer": "a"},
    {"id": "version_control_2", "domain": "Version control", "prompt": "Before merging a teammate's branch, what is a good practice?", "options": [{"id": "a", "text": "Review the changes and run relevant checks"}, {"id": "b", "text": "Delete the branch without looking"}, {"id": "c", "text": "Rename every file"}, {"id": "d", "text": "Commit generated secrets"}], "answer": "a"},
]


def public_assessment_questions():
    return [{key: question[key] for key in ("id", "domain", "prompt", "options")} for question in ASSESSMENT_QUESTIONS]


@bp.get("/profile/skill-assessment/questions")
@require_auth("student")
def get_skill_assessment_questions():
    return jsonify({"questions": public_assessment_questions(), "questionCount": len(ASSESSMENT_QUESTIONS)})


@bp.post("/profile/skill-assessment")
@require_auth("student")
def submit_skill_assessment():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}
    answers = data.get("answers")
    valid_answers = {question["id"]: {option["id"] for option in question["options"]} for question in ASSESSMENT_QUESTIONS}
    if not isinstance(answers, dict) or set(answers) != set(valid_answers) or any(not isinstance(answer, str) or answer not in valid_answers[question_id] for question_id, answer in answers.items()):
        return jsonify({"error": "Answer every question before submitting the assessment."}), 400
    domain_results = {}
    for question in ASSESSMENT_QUESTIONS:
        domain = question["domain"]
        result = domain_results.setdefault(domain, {"correct": 0, "total": 0})
        result["total"] += 1
        if answers[question["id"]] == question["answer"]:
            result["correct"] += 1
    for result in domain_results.values():
        result["signal"] = "Demonstrated strength" if result["correct"] == result["total"] else "Developing" if result["correct"] else "Build foundations"
    assessment = {"version": 1, "completedAt": now(), "totalCorrect": sum(item["correct"] for item in domain_results.values()), "totalQuestions": len(ASSESSMENT_QUESTIONS), "domains": [{"domain": domain, **result} for domain, result in domain_results.items()]}
    db.collection("studentProfiles").document(g.user["uid"]).set({"skillAssessment": assessment, "skillAssessmentAnswers": answers, "updatedAt": now()}, merge=True)
    return jsonify({"assessment": assessment, "message": "Skills assessment saved."})


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
