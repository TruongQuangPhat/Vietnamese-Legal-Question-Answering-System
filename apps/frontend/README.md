# VnLaw-QA Frontend

Minimal Next.js frontend scaffold for the VnLaw-QA product interface.

## Local Development

1. Copy `.env.example` to `.env.local`.
2. Set `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`.
3. Run `npm install`.
4. From the repository root, run `make backend-dev` in one terminal.
5. From the repository root, run `make frontend-dev` in another terminal.
6. Open `http://localhost:3000`.

The frontend expects the backend CORS setting to include
`http://localhost:3000`.

Fake mode returns stub Legal QA responses for local UI checks. It does not
require Qdrant, OpenRouter, embedding models, rerankers, or evaluation
workflows.

Equivalent direct commands:

```bash
cd /home/phat/AI_Project/VnLaw-QA
LEGAL_QA_SERVICE_MODE=fake uv run python -m uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000
```

```bash
cd /home/phat/AI_Project/VnLaw-QA/apps/frontend
npm run dev
```

Using `python -m uvicorn` ensures uvicorn runs with the project Python
environment managed by `uv`.

The Legal QA form calls the backend configured by `NEXT_PUBLIC_API_BASE_URL`.

## Vercel Production

Current production frontend:

```text
https://vnlaw-qa.vercel.app
```

Configure the Vercel project with the Next.js framework preset and:

```text
Root Directory: apps/frontend
```

Set the production build environment:

```env
NEXT_PUBLIC_API_BASE_URL=https://vnlaw-qa-backend.onrender.com
```

The backend must allow the deployed frontend origin:

```env
CORS_ALLOWED_ORIGINS=["https://vnlaw-qa.vercel.app"]
```

`NEXT_PUBLIC_API_BASE_URL` is public and embedded during `next build`; changing
it requires a new Vercel deployment. Do not place provider or database secrets
in any `NEXT_PUBLIC_*` variable.

The Render backend remains in real mode. Its liveness and readiness endpoints
pass, but Render Free cannot reliably serve real `/api/v1/legal-qa/ask`
requests because BGE-M3, Torch, and Transformers exceed the 512 MB memory
limit. Do not switch the backend to fake mode to mask this limitation.

## Container

Build the frontend image from the repository root:

```bash
make frontend-image
```

Run the image:

```bash
make frontend-container
```

Equivalent direct commands:

```bash
docker build -f docker/frontend/Dockerfile \
  -t vnlaw-qa-frontend:local \
  --build-arg NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 \
  .
```

```bash
docker run --rm -p 3000:3000 vnlaw-qa-frontend:local
```

Local smoke:

1. Run the backend on `http://localhost:8000` with `make backend-dev` or
   `make backend-container`.
2. Run the frontend container on `http://localhost:3000`.
3. Open `http://localhost:3000`.
4. Submit a Vietnamese legal question.
5. Confirm the fake backend response renders.

The frontend image contains no provider secrets. `NEXT_PUBLIC_API_BASE_URL` is
browser-facing, is inlined during the Next.js build, and must not contain secret
values. Keep it as `http://localhost:8000` for this local container workflow.

## Compose

Run the fake-mode backend and frontend stack from `docker-compose.yml` at the
repository root:

```bash
make stack-up
```

Equivalent direct command:

```bash
docker compose -f docker-compose.yml up --build
```

Open `http://localhost:3000`, submit a Vietnamese legal question, and confirm
the fake backend response renders. Stop the stack with:

```bash
make stack-down
```

Equivalent direct command:

```bash
docker compose -f docker-compose.yml down
```

The Compose stack keeps `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` because
the browser calls the backend through the host port. Do not change it to a
Docker service hostname until a separately scoped networking design needs it.

## API Client

TypeScript API types live in `src/types/legal-qa.ts`. The Legal QA client lives
in `src/lib/legal-qa-client.ts` and reads the backend base URL from
`NEXT_PUBLIC_API_BASE_URL`.
