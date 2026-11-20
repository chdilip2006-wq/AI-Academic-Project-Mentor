import logging
from flask import Flask, jsonify
from flask_cors import CORS
from .config import Config
from .extensions import initialize_mongodb, mongodb_available
from .routes import register_routes


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    CORS(app, origins=app.config["FRONTEND_ORIGINS"], allow_headers=["Authorization", "Content-Type"], methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    if not app.config.get("SECRET_KEY") or len(app.config["SECRET_KEY"]) < 32:
        raise RuntimeError("JWT_SECRET_KEY must be set to a random value of at least 32 characters.")
    initialize_mongodb(app.config)
    register_routes(app)

    from .utils.errors import ApiError

    @app.errorhandler(ApiError)
    def api_error(error):
        return jsonify({"error": error.message}), error.status

    @app.get("/api/health")
    def health():
        status = 200 if mongodb_available() else 503
        return jsonify({"status": "ok" if status == 200 else "degraded", "database": "connected" if status == 200 else "unavailable", "service": "ai-academic-project-mentor"}), status

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({"error": "The requested resource was not found."}), 404

    @app.errorhandler(413)
    def too_large(_error):
        return jsonify({"error": "The uploaded file exceeds the configured size limit."}), 413

    @app.errorhandler(Exception)
    def unexpected(error):
        app.logger.exception("Unhandled API error", exc_info=error)
        return jsonify({"error": "An unexpected server error occurred."}), 500

    return app
