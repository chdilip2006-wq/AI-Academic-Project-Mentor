from collections import defaultdict, deque
from functools import wraps
import threading
import time
from flask import current_app, jsonify, request

_lock = threading.Lock()
_requests = defaultdict(deque)


def rate_limit(max_requests, window_seconds):
    def decorate(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if current_app.config.get("TESTING") or not current_app.config.get("RATE_LIMITS_ENABLED", True):
                return view(*args, **kwargs)
            now = time.monotonic()
            key = (request.endpoint, request.remote_addr or "unknown")
            with _lock:
                events = _requests[key]
                while events and now - events[0] >= window_seconds:
                    events.popleft()
                if len(events) >= max_requests:
                    retry_after = max(1, int(window_seconds - (now - events[0])))
                    response = jsonify({"error": "Too many requests. Please wait before trying again."})
                    response.status_code = 429
                    response.headers["Retry-After"] = str(retry_after)
                    return response
                events.append(now)
            return view(*args, **kwargs)
        return wrapped
    return decorate
