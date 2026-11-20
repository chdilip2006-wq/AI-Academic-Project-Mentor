from datetime import datetime, timezone
from functools import wraps
import jwt
from flask import current_app, g, request, jsonify
from ..extensions import db


def require_auth(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            header = request.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                return jsonify({"error": "A bearer access token is required."}), 401
            try:
                claims = jwt.decode(header[7:], current_app.config["SECRET_KEY"], algorithms=["HS256"])
                user_doc = db.collection("users").document(claims.get("sub", "")).get()
                user = user_doc.to_dict() if user_doc.exists else None
                if not user: return jsonify({"error": "Your session is no longer valid. Please sign in again."}), 401
                g.user = {**user, "uid": user_doc.id}
            except jwt.ExpiredSignatureError:
                return jsonify({"error": "Your session expired. Please sign in again."}), 401
            except (jwt.InvalidTokenError, ValueError):
                return jsonify({"error": "The access token is invalid. Please sign in again."}), 401
            except Exception as error:
                current_app.logger.exception("Authentication lookup failed: %s", type(error).__name__)
                return jsonify({"error": "The account could not be loaded."}), 503
            if roles and g.user.get("role") not in roles:
                return jsonify({"error": "You do not have permission to perform this action."}), 403
            try:
                settings = db.collection("platformSettings").where("key", "==", "general").limit(1).stream()
                if g.user.get("role") != "admin" and settings and settings[0].to_dict().get("maintenanceMode") is True:
                    return jsonify({"error": "The platform is temporarily in maintenance mode. Please try again later."}), 503
            except Exception:
                pass
            return view(*args, **kwargs)
        return wrapped
    return decorator
