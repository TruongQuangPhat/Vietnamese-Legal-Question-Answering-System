# VnLaw-QA Frontend

Minimal Next.js frontend scaffold for the VnLaw-QA product interface.

## Local Development

1. Copy `.env.example` to `.env.local`.
2. Set `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`.
3. Run `npm install`.
4. Run `npm run dev`.

The frontend expects the backend CORS setting to include
`http://localhost:3000`.

To run the backend in fake mode for local UI checks:

```bash
cd /home/phat/AI_Project/VnLaw-QA
LEGAL_QA_SERVICE_MODE=fake uv run python -m uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000
```

Using `python -m uvicorn` ensures uvicorn runs with the project Python
environment managed by `uv`.

The Legal QA form calls the backend configured by `NEXT_PUBLIC_API_BASE_URL`.

## API Client

TypeScript API types live in `src/types/legal-qa.ts`. The Legal QA client lives
in `src/lib/legal-qa-client.ts` and reads the backend base URL from
`NEXT_PUBLIC_API_BASE_URL`.
