# AI Academic Project Mentor

A React and Flask workspace for academic project planning, mentoring, milestones, progress reports, and generated project documents.

## Architecture

- Frontend: React, Vite, React Router
- API: Python and Flask REST endpoints
- Database: MongoDB Atlas through one PyMongo client, with ObjectId identifiers
- Authentication: bcrypt password hashes and signed, one-hour JWT bearer tokens
- File storage: Cloudinary when configured; local `backend/local_uploads` storage for development
- AI: Groq-backed five-agent planning pipeline (Feasibility, Scope, Technology, Milestones, and Risk), plus conversational mentor
- Deployment: Vercel frontend and Render backend

The browser keeps the access token in `sessionStorage` for the current tab session. The API loads the user and role from MongoDB on each protected request. Public registration creates a student account only after required academic details and at least one named skill with a self-reported proficiency level are supplied. After account creation, students complete a short multiple-choice skills assessment; its domain-level signals help tailor feasibility and technology recommendations and can be retaken from the workspace. Programming languages, prior experience, and GitHub are optional. New users can request faculty access; an administrator must approve the pending request before the account receives faculty permissions. Bootstrap the first admin once through the trusted-shell `backend/create_admin.py` utility. Existing admins can grant additional admin access to another account from role management; self-role changes are blocked.

## Folder structure

```text
backend/
  app/agents/       Groq integration and planning agents
  app/middleware/   JWT authentication and role checks
  app/routes/       Flask REST endpoints
  app/services/     MongoDB adapter and Cloudinary/local storage service
  tests/            mocked database and AI tests
frontend/
  src/contexts/     JWT authentication context
  src/services/     centralized API client
  src/pages/        existing workspace pages
```

## Technical documentation

- [High-level architecture](HIGH_LEVEL_ARCHITECTURE.md) and [low-level architecture](LOW_LEVEL_ARCHITECTURE.md)
- [Database schema](DATABASE_SCHEMA.md), [API reference](API_REFERENCE.md), and [AI workflow](AI_WORKFLOW.md)
- [Project health rules](PROJECT_HEALTH.md), [testing guide](TESTING.md), and [end-to-end demo](DEMO_GUIDE.md)

## MongoDB Atlas and backend configuration

1. Create an Atlas cluster and a database user with access to the application database.
2. In Atlas, add the development machine or Render outbound access to the IP access list. Prefer a narrowly scoped allowlist where possible.
3. Choose **Connect ? Drivers ? Python** and copy the connection string. Replace the username and password; URL encode special characters in credentials. Do not commit the URI.
4. From PowerShell:

   ```powershell
   cd D:\iiproj\backend
   Copy-Item .env.example .env
   ```

   If `backend/.env` already exists, do not replace it. Add any missing settings from `.env.example` while preserving the configured credentials.

5. Set `MONGODB_URI` and a strong random `JWT_SECRET_KEY` in `backend/.env`. For example, generate a secret with:

   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

The backend pings MongoDB at startup, reuses one MongoClient, creates the unique `users.email` index and supporting relationship indexes, and uses the `MONGODB_DATABASE` database. An unreachable configured Atlas instance leaves the Flask process running in a degraded state and `/api/health` returns 503; database requests cannot succeed until connectivity is restored. No live Atlas connectivity is claimed by the mock-based tests.

Collections used by the application include `users`, `studentProfiles`, `projects`, `agentResults`, `milestones`, `progressUpdates`, `mentorChats`, `generatedDocuments`, and `facultyAssignments`. Platform settings and confirmed plan-adjustment suggestions use small supporting collections.

## Cloudinary and Groq

Set `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, and `CLOUDINARY_API_SECRET` only in `backend/.env` or deployment secrets. Never add these to Vite variables. With all three configured, file uploads use Cloudinary raw resources and MongoDB stores the public ID and secure URL. With credentials absent, the API uses the documented local-development directory `backend/local_uploads`; local files are not durable deployment storage. The implementation does not claim Cloudinary has been tested unless you configure and verify it.

Set `GROQ_API_KEY` and `GROQ_MODEL` in `backend/.env` for the conversational mentor and other AI features. Blueprint agents can each override those values with `AGENT_<NAME>_API_KEY` and `AGENT_<NAME>_MODEL` (`FEASIBILITY`, `SCOPE`, `TECHNOLOGY`, `MILESTONES`, `RISKS`). Each also has independent `MAX_OUTPUT_TOKENS`, `TIMEOUT_MS`, and optional input/output cost-per-million settings. Defaults use Groq GPT-OSS models; choose models enabled for your GroqCloud account. Leave cost rates unset unless you have verified the applicable price, so the dashboard does not present an invented cost.

All agent keys fall back to `GROQ_API_KEY`. Configure `AI_MAX_AGENT_REQUESTS_PER_PROJECT` and `AI_MAX_TOKENS_PER_PROJECT` to cap planner usage. A per-project usage panel shows each agent's model, request count, token totals, latency, status, and estimated cost when both provider usage and rates are available. `AI_MOCK_MODE=true` returns deterministic fixture outputs without making provider requests; use it only for local demonstrations/tests, never as evidence of real model output.

The planner stores each validated agent result immediately. If an agent fails, completed upstream outputs remain available and the project offers a resume action which retries from the failed agent through its downstream dependents. Repeated calls are guarded with per-project run locks, and planner/API retries are disabled by default. Tests always use isolated MongoDB fixtures and mocked AI; they never make Groq calls.

To bootstrap an administrator after configuring MongoDB, run the trusted-shell creator (it prompts for account details and does not print the password):

```powershell
cd D:\iiproj\backend
.\.venv\Scripts\python.exe create_admin.py
```

## Run on Windows 11

Open two PowerShell terminals.

Backend:

```powershell
cd D:\iiproj\backend
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env  # only if .env does not already exist
python run.py
```

Set `MONGODB_URI` and `JWT_SECRET_KEY` in `.env` before starting. If you already have a virtual environment, activate it and run `pip install -r requirements.txt`.

Frontend:

```powershell
cd D:\iiproj\frontend
Copy-Item .env.example .env  # only if .env does not already exist
npm install
npm run dev
```

Open the Vite URL printed in the terminal (usually `http://localhost:5173`). Set `VITE_API_URL` only when the Flask API is hosted somewhere other than `http://localhost:5000/api`.

## Tests and build

```powershell
cd D:\iiproj\backend
.\.venv\Scripts\python.exe -m pytest -q
cd D:\iiproj\frontend
npm run build
```

Install test-only dependencies with `pip install -r requirements-dev.txt`. Backend tests use an isolated in-memory MongoDB-compatible fixture, the explicit mock mode, and mocked provider responses. They do not modify Atlas data or spend Groq credits.

## Deployment

### Render

Create a Web Service from the repository; `render.yaml` configures the backend root, build command, and Gunicorn start command. Add `MONGODB_URI`, `JWT_SECRET_KEY` (Render can generate it), `FRONTEND_URL`, `GROQ_API_KEY`, and Cloudinary credentials as Render environment variables. Configure Atlas network access for Render. After deploying, check `/api/health` and create the first admin using a trusted shell with access to the same MongoDB URI.

### Vercel

Import the repository and set the Vercel project root to `frontend`. Configure `VITE_API_URL` to the deployed Flask API base, including `/api` (for example, `https://your-service.onrender.com/api`). Set the backend `FRONTEND_URL` to the Vercel origin and redeploy both sides after changing environment values.

## Security notes

- Password hashes are bcrypt hashes; password hashes are never returned by API responses.
- JWTs are signed with `JWT_SECRET_KEY`, expire after `JWT_ACCESS_TOKEN_EXPIRES` seconds, and roles are read from MongoDB rather than trusted from the token or request body.
- Authentication uses bearer headers rather than cookies; CORS is restricted to the origins listed in `FRONTEND_URL`.
- Keep `.env`, Atlas credentials, Cloudinary secrets, and generated signing keys private.
- Uploaded files are limited to 10 MB and a defined extension allowlist. Students can only manage files for their own projects; faculty access follows project assignments.
- Sensitive endpoints use process-local rate limits. Use a shared rate-limit store when scaling to multiple workers or instances.
