"""Shared MongoDB connection and a small document-store adapter for route compatibility."""
from datetime import datetime, timezone
import logging
from bson import ObjectId
from pymongo import MongoClient

mongo_client = None
_database = None
_mongo_error = None


def initialize_mongodb(config):
    global mongo_client, _database, _mongo_error
    _mongo_error = None
    uri = config.get("MONGODB_URI")
    if config.get("TESTING"):
        _database = config.get("MONGO_DATABASE")
        if _database is None:
            raise RuntimeError("Tests must supply an isolated MongoDB-compatible database fixture.")
    elif not uri:
        raise RuntimeError("MONGODB_URI is required. Set it in backend/.env.")
    else:
        try:
            mongo_client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            mongo_client.admin.command("ping")
            _database = mongo_client[config.get("MONGODB_DATABASE", "ai_academic_project_mentor")]
            _mongo_error = None
        except Exception as error:
            logging.getLogger(__name__).error("MongoDB connection unavailable (%s).", type(error).__name__)
            if mongo_client: mongo_client.close()
            mongo_client = None
            _database = None
            _mongo_error = type(error).__name__
            return
    if _database is None:
        raise RuntimeError("A MongoDB database is required.")
    _database.users.create_index("email", unique=True)
    for collection, fields in {
        "projects": [("studentId", 1), ("ownerId", 1), ("facultyId", 1)], "milestones": [("projectId", 1)],
        "progressUpdates": [("projectId", 1)], "mentorChats": [("projectId", 1)],
        "generatedDocuments": [("projectId", 1)], "facultyAssignments": [("studentId", 1), ("facultyId", 1)],
        "agentResults": [("projectId", 1)], "studentProfiles": [("uid", 1)],
        "riskAssessments": [("projectId", 1)], "planSuggestions": [("projectId", 1)],
        "blueprintHistory": [("projectId", 1)],
        "facultyAccessRequests": [("userId", 1), ("status", 1)],
    }.items():
        for field in fields:
            _database[collection].create_index([field])
    _database.facultyAssignments.create_index([("facultyId", 1), ("projectId", 1)], unique=True)


def _get_database():
    return _database


def close_mongodb():
    global mongo_client, _database, _mongo_error
    if mongo_client:
        mongo_client.close()
    mongo_client = _database = None
    _mongo_error = None


def mongodb_available():
    return _database is not None


def _id(value):
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(str(value))
    except Exception:
        return value


def _clean(doc):
    if not doc:
        return doc
    result = dict(doc)
    result["id"] = str(result.pop("_id"))
    for key, value in list(result.items()):
        if isinstance(value, ObjectId): result[key] = str(value)
        elif isinstance(value, datetime): result[key] = value.isoformat()
    return result


class Snapshot:
    def __init__(self, doc): self.doc = doc
    @property
    def exists(self): return self.doc is not None
    @property
    def id(self): return str(self.doc["_id"]) if self.doc else None
    def to_dict(self): return _clean(self.doc)


class Query:
    def __init__(self, collection, filters=None, max_results=None):
        self.collection, self.filters, self.max_results = collection, filters or {}, max_results
    def where(self, key, _operator, value):
        return Query(self.collection, {**self.filters, key: value}, self.max_results)
    def limit(self, count): return Query(self.collection, self.filters, count)
    def stream(self):
        cursor = self.collection.find(self.filters)
        if self.max_results: cursor = cursor.limit(self.max_results)
        return [Snapshot(d) for d in cursor]
    def document(self, doc_id=None): return Document(self.collection, doc_id)


class Document:
    def __init__(self, collection, doc_id=None):
        self.collection, self._doc_id = collection, _id(doc_id) if doc_id is not None else ObjectId()
        self.reference = self
    @property
    def id(self): return str(self._doc_id)
    def get(self): return Snapshot(self.collection.find_one({"_id": self._doc_id}))
    def set(self, value, merge=False):
        value = dict(value)
        value.setdefault("createdAt", datetime.now(timezone.utc))
        value["updatedAt"] = datetime.now(timezone.utc)
        if merge: self.collection.update_one({"_id": self._doc_id}, {"$set": value}, upsert=True)
        else: self.collection.replace_one({"_id": self._doc_id}, {**value, "_id": self._doc_id}, upsert=True)
    def update(self, value):
        changes = dict(value)
        changes.setdefault("updatedAt", datetime.now(timezone.utc))
        self.collection.update_one({"_id": self._doc_id}, {"$set": changes})
    def delete(self): self.collection.delete_one({"_id": self._doc_id})


class Collection:
    def __init__(self, collection): self.collection = collection
    def document(self, doc_id=None): return Document(self.collection, doc_id)
    def where(self, key, operator, value): return Query(self.collection).where(key, operator, value)
    def stream(self): return [Snapshot(d) for d in self.collection.find({})]


class Database:
    def __init__(self, database): self.database = database
    def collection(self, name): return Collection(self.database[name])


class DatabaseProxy:
    def __getattr__(self, name):
        database = _get_database()
        if database is None: raise RuntimeError("MongoDB has not been initialized.")
        return getattr(Database(database), name)


db = DatabaseProxy()
