# Testing and verification

## Automated checks

Backend tests use `mongomock` with `TESTING=True`, so they never connect to a configured Atlas URI. Planner tests use `AI_MOCK_MODE` or patched agent responses; the mock-mode test asserts that no Groq request is made. Focused mocks verify per-agent key/model/timeout/output-token configuration and usage accounting. The provider error test verifies that a 403 is not retried. No automated test spends Groq credits or mutates external data.

```powershell
cd D:\iiproj\backend
.\.venv\Scripts\python.exe -m pytest -q
cd D:\iiproj\frontend
npm run build
```

Coverage includes student-only registration, faculty request approval/rejection, one-time first-admin bootstrap, blocked self-role changes, JWT expiry/roles, profile updates, sequential planning and persistence, schema validation, partial-run resume without repeating successful agents, project AI usage summaries, mock mode, per-agent model configuration, progress and risks, mentoring, faculty assignment boundaries and summaries, admin functions, documents, local file storage, and invalid upload rejection.

## Manual integration checks

After configuring private environment variables and starting both services, follow [DEMO_GUIDE.md](DEMO_GUIDE.md). Calls to Groq, Atlas, and Cloudinary during manual integration are live external operations; use a development database and trigger each AI action only once as needed. Confirm `/api/health` before the workflow.

## Limits

The rate limiter is in-process memory. A multi-worker or multi-instance deployment should use a shared limiter store. The mock suite verifies API behavior but does not claim live provider credentials, Atlas network access, or Cloudinary account configuration.
