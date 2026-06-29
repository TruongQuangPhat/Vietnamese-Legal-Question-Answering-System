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

## API Client

TypeScript API types live in `src/types/legal-qa.ts`. The Legal QA client lives
in `src/lib/legal-qa-client.ts` and reads the backend base URL from
`NEXT_PUBLIC_API_BASE_URL`.
