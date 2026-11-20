from .auth import bp as auth_bp
from .profile import bp as profile_bp
from .projects import bp as projects_bp
from .planning import bp as planning_bp
from .progress import bp as progress_bp
from .mentor import bp as mentor_bp
from .documents import bp as documents_bp
from .faculty import bp as faculty_bp
from .admin import bp as admin_bp
from .risks import bp as risks_bp


def register_routes(app):
    for blueprint in (auth_bp, profile_bp, projects_bp, planning_bp, progress_bp, mentor_bp, documents_bp, faculty_bp, admin_bp, risks_bp):
        app.register_blueprint(blueprint, url_prefix="/api")
