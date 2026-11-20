import json
import logging
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from flask import current_app
from ..extensions import db
from ..services.store import now

logger = logging.getLogger(__name__)

AGENT_PROMPTS = [
    ("feasibility", "You are an academic project feasibility analyst. Assess the submitted idea's problem, technical feasibility, complexity, resources, likely time requirements, difficulty, and challenges. Return JSON with keys problemStatement, technicalFeasibility, complexity, requiredResources (array), timeEstimateWeeks (integer), expectedDifficulty, challenges (array), assumptions (array). Be honest about uncertainty and keep the estimate realistic for a student project."),
    ("scope", "You are an academic project scope analyst. Use the idea and feasibility context. Return JSON with keys title, problemStatement, objectives (array), functionalRequirements (array), nonFunctionalRequirements (array), coreFeatures (array), boundaries (array), expectedOutcomes (array). Keep scope achievable."),
    ("technology", "You are a technology advisor. Use profile, idea, feasibility and scope context. Recommend technologies specifically suited to this project and student's experience, not a generic default stack. Return one JSON object with keys frontend, backend, database, aiMl, developmentTools, recommendations. IMPORTANT: frontend, backend, database, aiMl, and developmentTools must each be arrays of objects. Every item must have exactly a string name and a string reasoning, for example: \"frontend\":[{\"name\":\"React\",\"reasoning\":\"Fits the interactive interface requirements.\"}]. Never return a category as a string or as a single object. Use an empty array only when no recommendation applies. The recommendations key must also be an array of {name, reasoning} objects."),
    ("milestones", "You are an academic project planner. Return JSON with keys estimatedWeeks (integer), milestones (array). Each milestone has week (integer), title (string), tasks (array of strings), deliverables (array of strings), dependencies (array of strings naming earlier milestone titles), completionCriteria (array of measurable strings), estimatedHours (integer). Every array must contain plain strings only; use [] when there are no dependencies. Do not return dependency objects, nulls, or a single string in place of an array. Provide a realistic week-wise plan."),
    ("risks", "You are a project risk analyst. Return JSON with keys risks (array). Each risk has category, description, severity (Low/Medium/High), probability (Low/Medium/High), mitigation. Include technical, time, resource and integration risks."),
]
AGENT_NAMES = tuple(name for name, _ in AGENT_PROMPTS)

_project_locks_guard = threading.Lock()
_project_locks = {}


class AgentRunError(RuntimeError):
    def __init__(self, agent, message, metrics=None):
        super().__init__(message)
        self.agent = agent
        self.metrics = metrics or {}


def planning_lock(project_id):
    with _project_locks_guard:
        return _project_locks.setdefault(project_id, threading.Lock())


class GroqRequestError(RuntimeError):
    def __init__(self, status_code, message):
        super().__init__(message)
        self.code = status_code


def _groq_access_failure(error, subject="Groq"):
    if _http_status(error) == 401:
        return "Groq rejected the API key (HTTP 401). Check GROQ_API_KEY in backend/.env."
    if _http_status(error) == 403:
        return f"{subject} access was denied by Groq (HTTP 403). Check key permissions and model access in GroqCloud."
    return f"{subject} request failed (HTTP {_http_status(error) or 'unknown'}). Check GroqCloud configuration."


def friendly_failure(error, service):
    message = str(error)
    if (
        message.startswith("Groq rejected the API key")
        or message.startswith("Groq access was denied")
        or message.startswith("Groq returned HTTP")
        or message.startswith("The Groq")
        or "access was denied (HTTP 403)" in message
    ):
        return message
    if "not configured" in message.lower():
        return "Groq is not configured. Add GROQ_API_KEY or the relevant agent-specific key to backend/.env and retry."
    return f"The {service} is temporarily unavailable. Please retry."


def _http_status(error):
    status = getattr(error, "code", None) or getattr(error, "status_code", None)
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


def _parse_response(text):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Groq returned an empty response.")
    return json.loads(text)


def _completion_text(response):
    choices = response.get("choices") or []
    message = choices[0].get("message", {}) if choices else {}
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return content


def _groq_completion(api_key, model, messages, timeout_ms, max_output_tokens):
    body = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "max_completion_tokens": max_output_tokens,
    }
    if model.startswith("openai/gpt-oss-"):
        body["reasoning_effort"] = "low"
    request_body = json.dumps(body).encode("utf-8")
    request = Request(
        f"{current_app.config.get('GROQ_BASE_URL', 'https://api.groq.com/openai/v1').rstrip('/')}/chat/completions",
        data=request_body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "ai-academic-project-mentor/1.0",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=max(1, timeout_ms / 1000)) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raw_body = error.read().decode("utf-8", errors="replace").strip()
        try:
            payload = json.loads(raw_body)
            error_payload = payload.get("error", {})
            message = error_payload.get("message") if isinstance(error_payload, dict) else None
            message = message or payload.get("message") or raw_body
        except (ValueError, AttributeError):
            message = raw_body or "Groq API returned an empty error response."
        raise GroqRequestError(error.code, message) from error
    except URLError as error:
        raise RuntimeError(f"Groq connection failed: {type(error.reason).__name__}.") from error


def generate_json(system_prompt, payload, retries=0):
    """General-purpose AI actions (mentor, documents, and other non-planner workflows)."""
    if current_app.config.get("AI_MOCK_MODE"):
        return mock_json(system_prompt, payload)
    api_key = current_app.config.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("Groq is not configured. Add GROQ_API_KEY to backend/.env and retry.")
    model = current_app.config.get("GROQ_MODEL", "openai/gpt-oss-20b")
    timeout_ms = current_app.config.get("AI_DEFAULT_TIMEOUT_MS", 60000)
    output_tokens = current_app.config.get("AI_DEFAULT_MAX_OUTPUT_TOKENS", 4096)
    messages = [
        {"role": "system", "content": system_prompt + "\n\nReturn only valid JSON."},
        {"role": "user", "content": "Input context:\n" + json.dumps(payload, ensure_ascii=False, default=str)},
    ]
    last_error = None
    for attempt in range(max(0, retries) + 1):
        try:
            response = _groq_completion(api_key, model, messages, timeout_ms, output_tokens)
            return _parse_response(_completion_text(response))
        except Exception as error:
            last_error = error
            status = _http_status(error)
            logger.warning("Groq request failed (attempt %s, HTTP %s): %s", attempt + 1, status or "unknown", type(error).__name__)
            if status in (401, 403):
                raise RuntimeError(_groq_access_failure(error)) from error
            if status == 404:
                detail = str(getattr(error, "message", "") or "Configured model or endpoint was not found.")
                raise RuntimeError(f"Groq returned HTTP 404: {detail[:240]}") from error
            if status is not None and 400 <= status < 500 and status not in (408, 429):
                raise RuntimeError(f"Groq rejected the request (HTTP {status}). Check the configured model and Groq API settings.") from error
            if attempt >= retries or (status is not None and status not in (408, 429, 500, 502, 503, 504)):
                break
            time.sleep(0.4 * (attempt + 1))
    raise RuntimeError("Groq could not produce a valid response. Please retry.") from last_error


def _agent_config(agent):
    prefix = f"AGENT_{agent.upper()}_"
    return {
        "model": current_app.config.get(prefix + "MODEL") or current_app.config.get("GROQ_MODEL", "openai/gpt-oss-20b"),
        "api_key": current_app.config.get(prefix + "API_KEY") or current_app.config.get("GROQ_API_KEY"),
        "timeout_ms": int(current_app.config.get(prefix + "TIMEOUT_MS", current_app.config.get("AI_DEFAULT_TIMEOUT_MS", 60000))),
        "max_output_tokens": int(current_app.config.get(prefix + "MAX_OUTPUT_TOKENS", current_app.config.get("AI_DEFAULT_MAX_OUTPUT_TOKENS", 4096))),
        "input_cost_per_million": current_app.config.get(prefix + "INPUT_COST_PER_MILLION"),
        "output_cost_per_million": current_app.config.get(prefix + "OUTPUT_COST_PER_MILLION"),
    }


def generate_agent_json(agent, system_prompt, payload, max_output_tokens=None):
    config = _agent_config(agent)
    model = config["model"]
    output_cap = min(config["max_output_tokens"], max_output_tokens) if max_output_tokens else config["max_output_tokens"]
    if current_app.config.get("AI_MOCK_MODE"):
        return mock_agent_result(agent), {
            "model": model, "status": "mock", "latencyMs": 0,
            "mode": "mock",
            "inputTokens": None, "outputTokens": None, "totalTokens": None,
            "estimatedCostUsd": None, "usageAvailable": False,
            "requestCount": 0, "maxOutputTokens": output_cap,
        }
    if not config["api_key"]:
        raise AgentRunError(agent, f"{agent} agent has no API key. Configure AGENT_{agent.upper()}_API_KEY or GROQ_API_KEY.")
    messages = [
        {"role": "system", "content": system_prompt + "\n\nReturn only valid JSON matching the required structure."},
        {"role": "user", "content": "Input context:\n" + json.dumps(payload, ensure_ascii=False, default=str)},
    ]
    started = time.perf_counter()
    try:
        response = _groq_completion(config["api_key"], model, messages, config["timeout_ms"], output_cap)
        result = _parse_response(_completion_text(response))
        if agent == "technology":
            result = _normalize_technology_output(result)
        elif agent == "milestones":
            result = _normalize_milestones_output(result)
        latency_ms = round((time.perf_counter() - started) * 1000)
        usage = response.get("usage") or {}
        input_tokens = usage.get("prompt_tokens")
        output_tokens = usage.get("completion_tokens")
        total_tokens = usage.get("total_tokens")
        price_in, price_out = config["input_cost_per_million"], config["output_cost_per_million"]
        estimated_cost = None
        if input_tokens is not None and output_tokens is not None and price_in is not None and price_out is not None:
            estimated_cost = round((input_tokens * float(price_in) + output_tokens * float(price_out)) / 1_000_000, 8)
        metrics = {
            "model": response.get("model", model), "status": "completed", "latencyMs": latency_ms,
            "mode": "live",
            "inputTokens": input_tokens, "outputTokens": output_tokens, "totalTokens": total_tokens,
            "estimatedCostUsd": estimated_cost, "usageAvailable": total_tokens is not None,
            "requestCount": 1, "maxOutputTokens": output_cap,
        }
        return result, metrics
    except Exception as error:
        status = _http_status(error)
        logger.warning("%s agent request failed (HTTP %s): %s", agent, status or "unknown", type(error).__name__)
        if status in (401, 403):
            message = _groq_access_failure(error, f"{agent} agent")
        elif status == 404:
            detail = str(getattr(error, "message", "") or "Configured model or endpoint was not found.")
            message = f"Groq returned HTTP 404 for {agent}: {detail[:240]}"
        elif status is not None and 400 <= status < 500 and status not in (408, 429):
            message = f"Groq rejected the {agent} agent request (HTTP {status}); check its model and request limits."
        else:
            message = f"The {agent} agent request failed: {type(error).__name__}."
        metrics = {
            "model": model, "status": "failed", "latencyMs": round((time.perf_counter() - started) * 1000),
            "mode": "live",
            "inputTokens": None, "outputTokens": None, "totalTokens": None,
            "estimatedCostUsd": None, "usageAvailable": False,
            "requestCount": 1, "maxOutputTokens": output_cap, "httpStatus": status,
        }
        raise AgentRunError(agent, message, metrics) from error


def _string(value):
    return isinstance(value, str) and bool(value.strip())


def _normalize_technology_output(result):
    """Coerce common singleton/scalar category shapes into the documented list schema."""
    if not isinstance(result, dict):
        return result
    categories = ("frontend", "backend", "database", "aiMl", "developmentTools", "recommendations")
    for category in categories:
        if category not in result:
            continue
        value = result.get(category)
        if value is None:
            result[category] = []
        elif isinstance(value, str):
            result[category] = [{"name": value.strip(), "reasoning": "Selected to fit the project requirements."}] if value.strip() else []
        elif isinstance(value, dict):
            if _string(value.get("name")):
                value.setdefault("reasoning", "Selected to fit the project requirements.")
                result[category] = [value]
            else:
                result[category] = [
                    {"name": str(name), "reasoning": str(reason)}
                    for name, reason in value.items()
                    if _string(str(name)) and _string(str(reason))
                ]
        elif isinstance(value, list):
            result[category] = [
                {"name": item.strip(), "reasoning": "Selected to fit the project requirements."}
                if isinstance(item, str) else item
                for item in value
            ]
    return result


def _milestone_text(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("title", "name", "description", "task", "deliverable", "dependency", "criterion", "text"):
            if _string(value.get(key)):
                return value[key].strip()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return ""


def _normalize_milestones_output(result):
    """Convert common singleton/object forms in milestone text arrays to strings."""
    if not isinstance(result, dict):
        return result
    milestones = result.get("milestones")
    if isinstance(milestones, dict):
        milestones = [milestones]
        result["milestones"] = milestones
    elif isinstance(milestones, str):
        try:
            parsed = json.loads(milestones)
            if isinstance(parsed, list):
                milestones = parsed
            elif isinstance(parsed, dict):
                milestones = [parsed]
            else:
                return result
            result["milestones"] = milestones
        except ValueError:
            return result
    if not isinstance(milestones, list):
        return result
    for item in milestones:
        if not isinstance(item, dict):
            continue
        for field in ("tasks", "deliverables", "dependencies", "completionCriteria"):
            if field not in item:
                continue
            value = item[field]
            if value is None:
                item[field] = []
            elif isinstance(value, (str, dict)):
                entry = _milestone_text(value)
                item[field] = [entry] if entry else []
            elif isinstance(value, list):
                item[field] = [entry for raw in value if (entry := _milestone_text(raw))]
    return result


def validate_agent_output(agent, result):
    required = {
        "feasibility": ("problemStatement", "technicalFeasibility", "complexity", "requiredResources", "timeEstimateWeeks", "expectedDifficulty", "challenges", "assumptions"),
        "scope": ("title", "problemStatement", "objectives", "functionalRequirements", "nonFunctionalRequirements", "coreFeatures", "boundaries", "expectedOutcomes"),
        "technology": ("frontend", "backend", "database", "aiMl", "developmentTools"),
        "milestones": ("estimatedWeeks", "milestones"),
        "risks": ("risks",),
    }
    if not isinstance(result, dict) or any(key not in result for key in required[agent]):
        raise ValueError(f"The {agent} agent returned an incomplete response.")
    array_fields = {
        "feasibility": ("requiredResources", "challenges", "assumptions"),
        "scope": ("objectives", "functionalRequirements", "nonFunctionalRequirements", "coreFeatures", "boundaries", "expectedOutcomes"),
        "technology": ("frontend", "backend", "database", "aiMl", "developmentTools"),
        "risks": ("risks",),
    }
    if agent in ("feasibility", "scope"):
        scalar_fields = ("problemStatement", "technicalFeasibility", "complexity", "expectedDifficulty") if agent == "feasibility" else ("title", "problemStatement")
        if any(not _string(result.get(key)) for key in scalar_fields):
            raise ValueError(f"The {agent} agent returned an invalid text field.")
    for key in array_fields.get(agent, ()):
        if not isinstance(result[key], list):
            raise ValueError(f"The {agent} agent returned an invalid '{key}' field.")
    if agent == "feasibility":
        if any(not _string(x) for key in array_fields[agent] for x in result[key]):
            raise ValueError("The feasibility agent returned invalid list items.")
        weeks = result["timeEstimateWeeks"]
        if not isinstance(weeks, int) or isinstance(weeks, bool) or not 1 <= weeks <= 104:
            raise ValueError("The feasibility agent returned an invalid time estimate.")
    if agent == "scope" and any(not _string(x) for key in array_fields[agent] for x in result[key]):
        raise ValueError("The scope agent returned invalid list items.")
    if agent == "technology":
        for category in array_fields[agent]:
            if any(not isinstance(item, dict) or not _string(item.get("name")) or not _string(item.get("reasoning")) for item in result[category]):
                raise ValueError("The technology agent returned an invalid recommendation.")
        if "recommendations" in result and (not isinstance(result["recommendations"], list) or any(not isinstance(item, dict) for item in result["recommendations"])):
            raise ValueError("The technology agent returned invalid recommendation details.")
    if agent == "milestones":
        weeks = result["estimatedWeeks"]
        if not isinstance(weeks, int) or isinstance(weeks, bool) or not 1 <= weeks <= 104:
            raise ValueError("The milestones agent returned an invalid timeline.")
        if not isinstance(result["milestones"], list) or not result["milestones"]:
            raise ValueError("The milestones agent must return at least one milestone.")
        for item in result["milestones"]:
            if not isinstance(item, dict) or not isinstance(item.get("week"), int) or not _string(item.get("title")):
                raise ValueError("The milestones agent returned an invalid milestone.")
            for field in ("tasks", "deliverables", "dependencies", "completionCriteria"):
                if not isinstance(item.get(field), list) or any(not _string(entry) for entry in item[field]):
                    raise ValueError(f"The milestones agent returned invalid {field}.")
            if "estimatedHours" in item and (not isinstance(item["estimatedHours"], int) or item["estimatedHours"] < 1):
                raise ValueError("The milestones agent returned invalid estimated hours.")
    if agent == "risks":
        for risk in result["risks"]:
            if not isinstance(risk, dict) or any(not _string(risk.get(key)) for key in ("category", "description", "severity", "probability", "mitigation")):
                raise ValueError("The risks agent returned an invalid risk.")
            if risk["severity"] not in ("Low", "Medium", "High") or risk["probability"] not in ("Low", "Medium", "High"):
                raise ValueError("The risks agent returned invalid probability or severity.")
    return result


def _profile_context(profile):
    profile = profile or {}
    return {key: profile[key] for key in ("department", "year", "skills", "programmingLanguages", "interests", "previousProjectExperience") if profile.get(key)}


def _technology_summary(technology):
    return {category: [{"name": item.get("name"), "reasoning": item.get("reasoning", "")[:160]} for item in technology.get(category, [])] for category in ("frontend", "backend", "database", "aiMl", "developmentTools")}


def _milestone_summary(plan):
    return {"estimatedWeeks": plan.get("estimatedWeeks"), "milestones": [{"week": item.get("week"), "title": item.get("title"), "deliverables": item.get("deliverables", [])} for item in plan.get("milestones", [])]}


def _input_for_agent(name, project, profile, results):
    base = {"project": {"title": project.get("title"), "idea": project.get("idea"), "domain": project.get("domain")}}
    feasibility = results.get("feasibility")
    scope = results.get("scope")
    technology = results.get("technology")
    milestones = results.get("milestones")
    if name == "feasibility":
        return {**base, "studentProfile": _profile_context(profile)}
    if name == "scope":
        return {**base, "feasibilitySummary": {key: feasibility[key] for key in ("problemStatement", "technicalFeasibility", "complexity", "timeEstimateWeeks", "challenges", "assumptions")}}
    if name == "technology":
        return {**base, "studentProfile": _profile_context(profile), "feasibilitySummary": {key: feasibility[key] for key in ("technicalFeasibility", "complexity", "requiredResources", "expectedDifficulty")}, "scopeSummary": {key: scope[key] for key in ("title", "problemStatement", "objectives", "coreFeatures", "boundaries")}}
    if name == "milestones":
        return {**base, "feasibilitySummary": {key: feasibility[key] for key in ("timeEstimateWeeks", "complexity", "expectedDifficulty")}, "scopeSummary": {key: scope[key] for key in ("title", "objectives", "coreFeatures", "boundaries", "expectedOutcomes")}, "technologySummary": _technology_summary(technology)}
    return {**base, "feasibilitySummary": {key: feasibility[key] for key in ("timeEstimateWeeks", "complexity", "challenges")}, "scopeSummary": {key: scope[key] for key in ("title", "coreFeatures", "boundaries")}, "technologySummary": _technology_summary(technology), "milestoneSummary": _milestone_summary(milestones)}


def _latest_for_agent(records, agent):
    items = [record for record in records if record.get("agent") == agent]
    if not items:
        return None
    return max(items, key=lambda item: item.get("sequence", 0))


def _project_usage(project_id):
    docs = db.collection("agentResults").where("projectId", "==", project_id).stream()
    records = [item.to_dict() or {} for item in docs]
    return {
        "requests": sum(int(item.get("requestCount", 0) or 0) for item in records),
        "tokens": sum(int(item.get("totalTokens", 0) or 0) for item in records),
    }


def run_planning(project_id, run_id, project, profile, start_index=0):
    records = [item.to_dict() or {} for item in db.collection("agentResults").where("projectId", "==", project_id).where("runId", "==", run_id).stream()]
    results = {}
    for index, (name, prompt) in enumerate(AGENT_PROMPTS):
        if index < start_index:
            prior = _latest_for_agent(records, name)
            if not prior or prior.get("status") != "completed" or not isinstance(prior.get("result"), dict):
                raise AgentRunError(name, f"Completed {name} result is missing; restart planning from this agent.")
            results[name] = validate_agent_output(name, prior["result"])
            continue
        current_usage = _project_usage(project_id)
        max_requests = int(current_app.config.get("AI_MAX_AGENT_REQUESTS_PER_PROJECT", 25))
        max_tokens = int(current_app.config.get("AI_MAX_TOKENS_PER_PROJECT", 100000))
        if current_usage["requests"] >= max_requests or current_usage["tokens"] >= max_tokens:
            raise AgentRunError(name, "Project AI usage limit reached. Increase the configured limit or start a new project to continue.")
        agent_ref = db.collection("agentResults").document()
        sequence = max([int(item.get("sequence", 0) or 0) for item in records] + [0]) + 1
        agent_config = _agent_config(name)
        is_mock = current_app.config.get("AI_MOCK_MODE")
        initial = {"projectId": project_id, "ownerId": project.get("ownerId"), "runId": run_id, "agent": name, "sequence": sequence, "status": "running", "mode": "mock" if is_mock else "live", "model": agent_config["model"], "requestCount": 0 if is_mock or not agent_config["api_key"] else 1, "createdAt": now()}
        agent_ref.set(initial)
        metrics = None
        try:
            max_output_tokens = max(1, min(agent_config["max_output_tokens"], max_tokens - current_usage["tokens"]))
            result, metrics = generate_agent_json(name, prompt, _input_for_agent(name, project, profile, results), max_output_tokens)
            validate_agent_output(name, result)
            metrics.update({"projectId": project_id, "ownerId": project.get("ownerId"), "runId": run_id, "agent": name, "sequence": sequence, "result": result, "status": "completed", "updatedAt": now()})
            agent_ref.update(metrics)
            records.append({**initial, **metrics})
            results[name] = result
        except Exception as error:
            metrics = metrics or getattr(error, "metrics", None) or {"model": agent_config["model"], "status": "failed", "requestCount": initial["requestCount"], "latencyMs": 0, "usageAvailable": False, "inputTokens": None, "outputTokens": None, "totalTokens": None, "estimatedCostUsd": None}
            metrics.update({"projectId": project_id, "ownerId": project.get("ownerId"), "runId": run_id, "agent": name, "sequence": sequence, "status": "failed", "error": str(error)[:400], "updatedAt": now()})
            agent_ref.update(metrics)
            raise AgentRunError(name, str(error)) from error
    blueprint = {**results["scope"], "feasibility": results["feasibility"], "technology": results["technology"], "planning": results["milestones"], "risks": results["risks"], "generatedAt": None}
    return results, blueprint


def mock_agent_result(agent):
    samples = {
        "feasibility": {"problemStatement": "A focused academic prototype can address the stated need.", "technicalFeasibility": "Feasible with a small, testable first release.", "complexity": "Medium", "requiredResources": ["Development environment", "Representative test data"], "timeEstimateWeeks": 8, "expectedDifficulty": "Medium", "challenges": ["Keep the initial feature set manageable"], "assumptions": ["The student can access a development machine"]},
        "scope": {"title": "Academic Project Prototype", "problemStatement": "The project needs a clear, testable solution to its stated problem.", "objectives": ["Build a working prototype", "Evaluate it against defined requirements"], "functionalRequirements": ["Allow users to complete the core workflow"], "nonFunctionalRequirements": ["Provide clear validation and error feedback"], "coreFeatures": ["Core workflow", "Basic reporting"], "boundaries": ["Exclude production-scale integrations"], "expectedOutcomes": ["Demonstrable prototype and documentation"]},
        "technology": {"frontend": [{"name": "React", "reasoning": "Suitable for an interactive project interface."}], "backend": [{"name": "Flask", "reasoning": "Supports a compact modular API."}], "database": [{"name": "MongoDB", "reasoning": "Stores flexible project records."}], "aiMl": [], "developmentTools": [{"name": "Git", "reasoning": "Tracks implementation changes."}], "recommendations": []},
        "milestones": {"estimatedWeeks": 4, "milestones": [{"week": 1, "title": "Requirements and design", "tasks": ["Confirm scope"], "deliverables": ["Requirements outline"], "dependencies": [], "completionCriteria": ["Objectives and core requirements are documented"], "estimatedHours": 8}, {"week": 2, "title": "Build core workflow", "tasks": ["Implement the main use case"], "deliverables": ["Working prototype"], "dependencies": ["Requirements and design"], "completionCriteria": ["Main workflow runs locally"], "estimatedHours": 16}, {"week": 3, "title": "Test and refine", "tasks": ["Test normal and error cases"], "deliverables": ["Test notes"], "dependencies": ["Build core workflow"], "completionCriteria": ["Key cases pass"], "estimatedHours": 10}, {"week": 4, "title": "Document and demonstrate", "tasks": ["Prepare the demo"], "deliverables": ["Final report and demo"], "dependencies": ["Test and refine"], "completionCriteria": ["Demo and report are ready"], "estimatedHours": 8}]},
        "risks": {"risks": [{"category": "Time management", "description": "Unplanned scope growth could delay completion.", "severity": "Medium", "probability": "Medium", "mitigation": "Prioritize the core workflow and defer optional features."}]},
    }
    return samples[agent]


def mock_json(system_prompt, payload):
    prompt = system_prompt.lower()
    if "mentor" in prompt:
        return {"answer": "Mock mode is enabled. Use the project plan to break the next task into a small testable step.", "suggestedNextSteps": ["Choose one milestone task", "Define how to verify it"]}
    if "risk" in prompt:
        return {"summary": "Mock risk review based on the supplied project context.", **mock_agent_result("risks")}
    if "plan adjustment" in prompt:
        return {"summary": "Mock adjustment: keep completed work and reduce scope on the next milestone.", "proposedChanges": [], "tradeoffs": ["Fewer optional features"]}
    if "academic writing assistant" in prompt:
        return {"title": "Mock project document", "content": "Mock document preview. Replace AI_MOCK_MODE with false to generate from Groq."}
    if "summarize the student's project" in prompt:
        return {"summary": "Mock faculty summary based on the saved project data."}
    return {}
