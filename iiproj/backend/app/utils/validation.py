from .errors import ApiError


def json_body(required=None):
    from flask import request
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise ApiError("A JSON object is required.")
    for key in required or []:
        if key not in value:
            raise ApiError(f"'{key}' is required.")
    return value


def required_text(data, key, maximum=5000, minimum=1):
    value = data.get(key)
    if not isinstance(value, str) or len(value.strip()) < minimum or len(value) > maximum:
        raise ApiError(f"'{key}' must be between {minimum} and {maximum} characters.")
    return value.strip()
