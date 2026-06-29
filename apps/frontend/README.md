# VnLaw-QA Frontend

Minimal Next.js frontend scaffold for the VnLaw-QA product interface.

## Local Development

1. Copy `.env.example` to `.env.local`.
2. Set `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`.
3. Run `npm install`.
4. Run `npm run dev`.

The frontend expects the backend CORS setting to include
`http://localhost:3000`.

This scaffold does not call the backend yet. The Legal QA ask form and API
client will be added in a later increment.
