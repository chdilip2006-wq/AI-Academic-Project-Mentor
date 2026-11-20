from dotenv import dotenv_values
from pymongo.uri_parser import parse_uri

values = dotenv_values(".env")
uri = values.get("MONGODB_URI") or ""
print("scheme:", uri.split(":", 1)[0] if ":" in uri else "missing")
try:
    parsed = parse_uri(uri)
    print("parse: valid; host_count:", len(parsed.get("nodelist", [])), "; database:", bool(parsed.get("database")))
except Exception as error:
    print("parse: invalid; error_type:", type(error).__name__)
