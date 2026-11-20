import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
    DEBUG = os.getenv("FLASK_DEBUG", "").lower() in ("1", "true", "yes") or os.getenv("FLASK_ENV", "production") == "development"
    TESTING = False
    FRONTEND_ORIGINS = [origin.strip() for origin in os.getenv("FRONTEND_URL", "http://localhost:5173").split(",") if origin.strip()]
    MONGODB_URI = os.getenv("MONGODB_URI")
    MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "ai_academic_project_mentor")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
    AI_MOCK_MODE = os.getenv("AI_MOCK_MODE", "false").strip().lower() in ("1", "true", "yes", "on")
    AI_DEFAULT_TIMEOUT_MS = int(os.getenv("AI_DEFAULT_TIMEOUT_MS", "60000"))
    AI_DEFAULT_MAX_OUTPUT_TOKENS = int(os.getenv("AI_DEFAULT_MAX_OUTPUT_TOKENS", "4096"))
    AI_MAX_AGENT_REQUESTS_PER_PROJECT = int(os.getenv("AI_MAX_AGENT_REQUESTS_PER_PROJECT", "25"))
    AI_MAX_TOKENS_PER_PROJECT = int(os.getenv("AI_MAX_TOKENS_PER_PROJECT", "100000"))
    AI_PLANNING_LOCK_TTL_SECONDS = int(os.getenv("AI_PLANNING_LOCK_TTL_SECONDS", "1200"))
    JWT_ACCESS_TOKEN_EXPIRES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES", "3600"))
    CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")
    LOCAL_UPLOAD_DIR = os.getenv("LOCAL_UPLOAD_DIR", "local_uploads")
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_UPLOAD_MB", "10")) * 1024 * 1024


for _agent in ("FEASIBILITY", "SCOPE", "TECHNOLOGY", "MILESTONES", "RISKS"):
    _model_default = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    setattr(Config, f"AGENT_{_agent}_MODEL", os.getenv(f"AGENT_{_agent}_MODEL", _model_default))
    setattr(Config, f"AGENT_{_agent}_API_KEY", os.getenv(f"AGENT_{_agent}_API_KEY"))
    setattr(Config, f"AGENT_{_agent}_TIMEOUT_MS", int(os.getenv(f"AGENT_{_agent}_TIMEOUT_MS", os.getenv("AI_DEFAULT_TIMEOUT_MS", "60000"))))
    setattr(Config, f"AGENT_{_agent}_MAX_OUTPUT_TOKENS", int(os.getenv(f"AGENT_{_agent}_MAX_OUTPUT_TOKENS", "4096")))
    for _direction in ("INPUT", "OUTPUT"):
        _cost = os.getenv(f"AGENT_{_agent}_{_direction}_COST_PER_MILLION")
        setattr(Config, f"AGENT_{_agent}_{_direction}_COST_PER_MILLION", float(_cost) if _cost not in (None, "") else None)
