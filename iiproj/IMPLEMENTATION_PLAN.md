# Implementation plan (migrated architecture)

## Current application
- React + Vite frontend with the existing academic workspace UI and React Router.
- Flask REST API with modular route, middleware, agent, and service packages.
- MongoDB Atlas/PyMongo persistence, ObjectId identifiers, relationship indexes, and timestamps.
- JWT bearer authentication with bcrypt hashes and database-backed role checks.
- Cloudinary file storage with a documented local-development fallback.
- Groq-backed five-agent planning orchestrator and project-specific conversational mentor.

## Domain collections
`users`, `studentProfiles`, `projects`, `agentResults`, `milestones`, `progressUpdates`, `mentorChats`, `generatedDocuments`, `facultyAssignments`, plus settings and plan adjustment support collections.

## Remaining deployment configuration
1. Configure a MongoDB Atlas URI and network allowlist.
2. Set a strong JWT secret and create the first administrator through the trusted-shell bootstrap script.
3. Configure Cloudinary credentials for durable file storage.
4. Configure `GROQ_API_KEY` for AI routes (not needed for mocked verification).
5. Set Vercel API URL and Render frontend origin.

## Verification
Use backend pytest with mocked MongoDB-compatible data and mocked AI responses, then build the Vite frontend. No migration test sends prompts to Groq or mutates a production database.

## AI usage and resumable planning
- Five planner agents have independent model, optional API key, request timeout, output-token cap, and optional model-rate configuration. Agent keys fall back to `GROQ_API_KEY`.
- The sequential orchestrator validates each output, stores it immediately, and retries only the failed agent plus downstream agents. Project-level MongoDB locking prevents duplicate concurrent runs.
- Agent token usage, latency, model, status, request count, and cost estimate when configured are available from the project AI-usage endpoint and project workspace panel.
- `AI_MOCK_MODE=true` runs deterministic fixtures without Groq; test suites use isolated databases and mocks only.

## Registration and role approval
- Public registration always creates a student; optional faculty access requests are stored as `PENDING` and reviewed by an admin before a role is changed to faculty.
- Direct faculty role assignment is blocked. Existing admins can promote another account to admin, while self-role changes are rejected.
- `backend/create_admin.py` is a one-time, trusted-shell first-admin bootstrap with an atomic MongoDB bootstrap lock; subsequent admin access is granted by an authenticated admin.
