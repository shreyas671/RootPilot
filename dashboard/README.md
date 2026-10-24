# RootPilot operator console

This directory contains the RootPilot production operations dashboard. It is a standard Next.js application designed for Vercel. It lists jobs and investigation reports, displays retrieval and model provenance, and supports approve/reject review decisions.

The default API endpoint comes from `NEXT_PUBLIC_ROOTPILOT_API_URL` and remains editable in the interface. A bearer token is held only in React state and is not written to browser storage. The API base URL is persisted locally for convenience.

## Development

```bash
npm ci
npm run dev
```

Open `http://localhost:3000`, enter the RootPilot API base URL, and optionally enter a JWT when API authentication is enabled.

Copy `.env.example` to `.env.local` to provide a non-local default API URL.

## Verification

```bash
npm audit --omit=dev --audit-level=high
npm run lint
npm test
```

## Vercel

Import the repository into a Vercel Hobby project and set the project Root Directory to `dashboard`. The framework is detected as Next.js. Set:

```text
NEXT_PUBLIC_ROOTPILOT_API_URL=https://YOUR-API.onrender.com
NEXT_PUBLIC_SITE_URL=https://YOUR-PROJECT.vercel.app
```

Redeploy after changing either public variable because Next.js includes `NEXT_PUBLIC_*` values in the browser bundle at build time. The full backend and CORS setup is documented in `../docs/deployment-vercel-render.md`.
