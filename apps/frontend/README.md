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
The frontend `.env.example` is local-only by default and contains no secrets.
`NEXT_PUBLIC_API_BASE_URL` is public and embedded into the browser bundle at
build time.

## Answer, Evidence, and Warnings UX

Normal users see legal basis information, not backend retrieval/debug
metadata. Assistant answers keep inline citation anchors such as `[E1]`, but
those anchors only open the legal-basis drawer. The UI does not show scores,
chunk IDs, evidence IDs, vector IDs, raw metadata, or JSON payloads in the
normal answer surface.

Each completed assistant answer shows a footer action such as:

```text
Đã sử dụng 2 căn cứ pháp lý
```

Clicking it opens a right-side drawer on desktop or a bottom sheet on smaller
screens. The drawer displays source names, legal positions such as article or
clause labels, readable evidence text when present, and an optional source
link. If citations are present but evidence text was not included in the API
response, the drawer shows a friendly message instead of falling back to
technical identifiers.

While a request is pending, the answer area shows a compact progress card with
a spinner and a safe current stage such as receiving the question, finding
legal basis, or creating the answer. After completion, the process display is
collapsed by default and can be expanded with `Xem quá trình` to show a
timeline-style summary. It must not display hidden chain-of-thought, private
model reasoning, prompts, raw evidence payloads, raw metadata fields, or secret
values.

Backend warning names are never shown raw in the normal UI. Evidence caution
warnings are not shown as top-level answer warnings; they may appear only as
subtle context in expanded details. Severe retrieval/infrastructure warnings
use concise user-friendly wording and are deduplicated.

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
NEXT_PUBLIC_API_BASE_URL=https://vnlaw-backend-prod-phat.azurewebsites.net
```

Production frontend should use the accepted Azure production backend. Render
should not be used as the normal backend. In browser DevTools Network, Legal QA
requests should go to:

```text
https://vnlaw-backend-prod-phat.azurewebsites.net/api/v1/legal-qa/ask
```

If the production bundle is missing this environment variable, the frontend
uses the accepted Azure backend as a production-safe default so a valid submit
still starts `/api/v1/legal-qa/ask`. Keep the Vercel environment set anyway;
the explicit environment value remains the primary deployment configuration and
prevents ambiguity when backend URLs change.

If production Network requests show localhost, for example
`http://localhost:8000/api/v1/legal-qa/ask`, the deployed bundle is stale or
was built before the production-safe guard. If requests go to `onrender.com`,
the Vercel environment is stale. In both cases, redeploy Vercel Production with
the Azure backend URL.

For Azure backend UI smoke before any future frontend production change, first
set a Vercel Preview deployment to:

```env
NEXT_PUBLIC_API_BASE_URL=https://vnlaw-backend-staging-phat-feg8eabzgxhuafc3.japaneast-01.azurewebsites.net
```

The Azure backend must allow the exact Vercel Preview origin before browser
traffic will pass CORS. Vercel Preview URLs are deployment-specific, so add the
actual preview URL shown by Vercel to the Azure App Service
`CORS_ALLOWED_ORIGINS` JSON array and restart the Azure App Service after
saving the setting.

Manual Preview smoke:

1. Redeploy Vercel Preview after setting `NEXT_PUBLIC_API_BASE_URL`.
2. Copy the exact Vercel Preview URL.
3. Add that exact origin to Azure `CORS_ALLOWED_ORIGINS`.
4. Restart Azure App Service.
5. Open the Vercel Preview frontend.
6. Open browser DevTools and select the Network tab.
7. Submit exactly one safe Vietnamese legal question:

   ```text
   Theo Bộ luật Dân sự Việt Nam, hợp đồng dân sự có thể bị vô hiệu trong những trường hợp nào?
   ```

8. Verify the request URL goes to the Azure backend, not Render.
9. Verify the UI displays a response and no browser CORS error appears.

After the preview UI smoke passes, keep Vercel Production pointed at the
accepted Azure production backend and redeploy if the environment changed.
Render may be kept only as a legacy rollback value until decommission is
reviewed separately.

The backend must allow the deployed frontend origin:

```env
CORS_ALLOWED_ORIGINS=["https://vnlaw-qa.vercel.app"]
```

`NEXT_PUBLIC_API_BASE_URL` is public and embedded during `next build`; changing
it requires a new Vercel deployment. Do not place provider or database secrets
in any `NEXT_PUBLIC_*` variable.

The legacy Render backend may still exist for rollback context, but Render Free
cannot reliably serve real `/api/v1/legal-qa/ask` requests because BGE-M3,
Torch, and Transformers exceed the 512 MB memory limit. Do not use Render as
the normal backend and do not switch any backend to fake mode to mask this
limitation.

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
