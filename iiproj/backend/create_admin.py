"""Bootstrap the first administrator from a trusted shell; never an HTTP endpoint."""
import getpass
import os
import re
from datetime import datetime, timedelta, timezone

import bcrypt
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError


def create_first_admin(database, email, name, password):
    email = email.strip().lower()
    name = name.strip()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ValueError("Enter a valid email address.")
    if not name or len(name) > 120 or not isinstance(password, str) or len(password) < 12 or len(password.encode("utf-8")) > 72:
        raise ValueError("Name must be 1 to 120 characters and password 12 to 72 characters.")
    timestamp = datetime.now(timezone.utc)
    bootstrap = database.adminBootstrap
    bootstrap.find_one_and_delete({"_id": "first-admin", "status": "started", "createdAt": {"$lt": timestamp - timedelta(minutes=10)}})
    try:
        bootstrap.insert_one({"_id": "first-admin", "status": "started", "createdAt": timestamp})
    except DuplicateKeyError as error:
        raise RuntimeError("An administrator already exists or first-admin bootstrap is in progress.") from error
    try:
        if database.users.count_documents({"role": "admin"}, limit=1):
            raise RuntimeError("An administrator already exists. Additional admin access must be granted by an authenticated admin.")
        result = database.users.insert_one({
            "email": email,
            "name": name,
            "role": "admin",
            "passwordHash": bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
            "createdAt": timestamp,
            "updatedAt": timestamp,
        })
        bootstrap.update_one({"_id": "first-admin", "status": "started"}, {"$set": {"status": "completed", "adminId": str(result.inserted_id), "completedAt": datetime.now(timezone.utc)}})
        return str(result.inserted_id)
    except Exception:
        bootstrap.delete_one({"_id": "first-admin", "status": "started"})
        raise


def main():
    load_dotenv()
    uri = os.getenv("MONGODB_URI")
    database_name = os.getenv("MONGODB_DATABASE", "ai_academic_project_mentor")
    if not uri:
        raise SystemExit("Set MONGODB_URI in backend/.env before bootstrapping the first administrator.")
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    try:
        database = client[database_name]
        client.admin.command("ping")
        database.users.create_index("email", unique=True)
        if database.users.count_documents({"role": "admin"}, limit=1):
            raise SystemExit("An administrator already exists. Sign in as admin to grant additional admin access.")
        email = input("Administrator email: ").strip()
        name = input("Administrator name: ").strip()
        password = getpass.getpass("Password (12+ characters): ")
        create_first_admin(database, email, name, password)
    except DuplicateKeyError:
        raise SystemExit("An account with that email already exists; an authenticated admin can update its role.")
    finally:
        client.close()
    print("First administrator account created.")


if __name__ == "__main__":
    main()
