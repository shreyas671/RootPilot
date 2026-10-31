# Free deployment: Vercel, Render, and Neon

This is RootPilot's zero-platform-cost hobby/demo topology:

```text
Browser
  -> Vercel Hobby: Next.js dashboard
       -> HTTPS + short-lived bearer token
            -> Render Free: FastAPI API + embedded queue worker
                 -> Neon Free: PostgreSQL + pgvector
                 -> Private OpenAI-compatible embeddings and structured analysis
```

The API and queue worker share one Render process because Render does not offer
a free background-worker instance. Neon replaces Render Postgres because a free
Render database expires after 30 days. Alembic migrations run every time the
Render container starts; they are transactional and no-op when already current.

## What is and is not free

- Vercel Hobby is free for personal, non-commercial projects within its usage
  limits.
- Render's Free web service costs $0, spins down after 15 idle minutes, and can
  take about a minute to wake up.
- Neon Free provides persistent serverless PostgreSQL within its usage limits.
- Model-gateway access is separate from hosting and requires an
  authorized developer key. RootPilot cannot generate embeddings or assessments
  when the configured gateway or models are unavailable.

This topology is suitable for learning, portfolio demonstrations, and light
personal use. It is not an always-on production topology.

## 1. Create the free Neon database

1. Create a Neon Free project in a US East region close to Render Virginia.
2. Open **Connect**, select the project's main branch, and copy the direct
   PostgreSQL connection string. It normally resembles:

   ```text
   postgresql://USER:PASSWORD@HOST.neon.tech/DATABASE?sslmode=require&channel_binding=require
   ```

3. Keep the complete connection string for Render's `DATABASE_URL` prompt.

RootPilot converts the URL to SQLAlchemy's asyncpg driver and normalizes Neon's
SSL parameters. The first Render start runs all Alembic migrations, including
`CREATE EXTENSION vector`.

## 2. Prepare authentication values

Generate a JWT signing secret locally:

```bash
openssl rand -hex 32
```

Keep this value temporarily. You will enter the same value in Render as
`AUTH_JWT_SECRET` and use it locally to create dashboard tokens. Do not put it in
Vercel or commit it to Git.

Decide the Vercel project name before creating Render. The expected production
origin will be `https://YOUR-PROJECT.vercel.app`.

## 3. Create the free Render backend

1. In Render, choose **New > Blueprint**.
2. Connect this GitHub repository and select the root-level `render.yaml`.
3. Confirm that `rootpilot-api` uses the **Free** plan. The Blueprint must not
   contain a background worker or a Render database.
4. Enter the prompted values:

   ```text
   DATABASE_URL=<the complete Neon connection string>
   OPENAI_API_KEY=<your private model-gateway key>
   LANGSMITH_API_KEY=<your LangSmith API key>
   AUTH_JWT_SECRET=<the 64-character value generated above>
   CORS_ORIGINS=["https://YOUR-PROJECT.vercel.app"]
   ```

5. Apply the Blueprint and wait for the deployment to become healthy.
   LangSmith tracing remains disabled initially. After the service is healthy,
   set `LANGSMITH_TRACING=true` in Render to begin exporting traces to the
   `rootpilot-production` project. Use `LANGSMITH_HIDE_INPUTS=true` and/or
   `LANGSMITH_HIDE_OUTPUTS=true` when incident evidence must not leave the
   application payload.
6. Copy the assigned API URL, for example:

   ```text
   https://rootpilot-api.onrender.com
   ```

Verify:

```text
https://YOUR-API.onrender.com/health
https://YOUR-API.onrender.com/ready
```

The container start command runs `alembic upgrade head` before Uvicorn,
including the ReAct trajectory-provenance migration. The FastAPI lifespan then
starts the queue worker inside the same process. One free web instance therefore
serves requests and processes queued investigations. The Blueprint enables
`INVESTIGATION_MODE=react`; set it to `single_pass` only when a rollback is
required.

A ReAct investigation makes multiple analysis-model calls—one per decision plus
the final assessment—and may make multiple embedding calls for targeted runbook
queries. Confirm that the private gateway quota can support the bounded values
in `REACT_MAX_ITERATIONS` and `REACT_MAX_TOOL_CALLS`.

## 4. Create the Vercel frontend

1. In Vercel, choose **Add New > Project** and import this GitHub repository.
2. Choose the Vercel **Hobby** plan.
3. Set **Root Directory** to `dashboard`.
4. Keep the detected **Next.js** framework preset.
5. Add these Production environment variables:

   ```text
   NEXT_PUBLIC_ROOTPILOT_API_URL=https://YOUR-API.onrender.com
   NEXT_PUBLIC_SITE_URL=https://YOUR-PROJECT.vercel.app
   ```

6. Deploy.

If Vercel assigns a different hostname, update `CORS_ORIGINS` on Render to the
exact HTTPS origin (without a trailing slash), then redeploy the Render service.

## 5. Create a dashboard access token

Free Render services do not provide shell access. Generate the token locally
with the same secret you entered in Render:

```bash
AUTH_JWT_SECRET='PASTE-THE-SAME-SECRET' \
AUTH_JWT_ISSUER='rootpilot-render' \
AUTH_JWT_AUDIENCE='rootpilot-api' \
uv run python -m apps.metadata_service.commands.create_access_token \
  --subject your-email@example.com \
  --role operator \
  --ttl-minutes 60
```

Paste the printed token into the dashboard's **Bearer token** field. The token
stays only in the current tab's React state and disappears after a refresh.

Roles are hierarchical:

- `viewer`: read jobs, reports, evidence, and audit events.
- `operator`: viewer access plus queueing and approve/reject decisions.
- `admin`: all current permissions.

## 6. Verify the complete flow

1. Open the Vercel URL. The first API request might wait about a minute while
   Render wakes from an idle state.
2. Confirm the API URL, paste an operator token, and select **Connect workspace**.
3. Queue one prepared incident.
4. Keep the dashboard/API active while the embedded worker processes the job.
5. Refresh the dashboard and open the completed report.
6. Inspect the ReAct tool timeline, stopping reason, citations, retrieval
   scores, and model/retrieval provenance.
7. Approve the report, or reject it with feedback.
8. Reopen it and verify the immutable review event.

## Free-tier behavior and troubleshooting

### Cold starts

Render spins the service down after 15 idle minutes. A new request wakes it and
can take about a minute. The embedded worker exists only while the web service is
awake, so queued jobs do not progress during a spin-down. Opening the dashboard
or `/health` wakes the service.

### Dashboard cannot connect

- Open the Render `/ready` URL first and wait for a successful response.
- Confirm `NEXT_PUBLIC_ROOTPILOT_API_URL` uses HTTPS and redeploy Vercel after a
  change.
- Confirm `CORS_ORIGINS` is a JSON list containing the exact Vercel origin.

### Render fails during startup

- Inspect the service logs for Alembic, pgvector, or database TLS errors.
- Confirm `DATABASE_URL` is the complete Neon URL.
- Confirm all four prompted Render variables are present.
- Verify the Neon project has not exhausted its free compute/storage allowance.

### Jobs remain pending or fail

- Wake the Render service and keep it active while testing.
- Inspect Render logs for `embedded_worker_stopped` or model-gateway errors.
- Confirm the gateway key is valid and authorized for the private embedding and
  analysis model identifiers configured on Render.
- The supervisor retries a failed embedded worker without taking the API down.

### 401 or 403

- `401`: the token is missing, expired, incorrectly signed, or has the wrong
  issuer/audience.
- `403`: the token is valid but lacks the required role.
- Generate another local token using the exact secret stored in Render.

## Moving beyond the free demo topology

For dependable production operation, move the embedded worker back to a
dedicated worker service, use an always-on web service, use a database plan with
backups, and replace manually issued HS256 tokens with an OIDC/JWKS identity
provider. The queue leasing design already supports multiple worker replicas.
