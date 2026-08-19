# RootPilot operator console

This directory contains the RootPilot production operations dashboard. It is a Vinext/Next.js application that lists jobs and investigation reports, displays retrieval and model provenance, and supports approve/reject review decisions.

The API endpoint is configurable in the interface. A bearer token is held only in React state and is not written to browser storage. The API base URL is persisted locally for convenience.

## Development

```bash
npm ci
npm run dev
```

Open `http://localhost:3000`, enter the RootPilot API base URL, and optionally enter a JWT when API authentication is enabled.

## Verification

```bash
npm audit --omit=dev --audit-level=high
npm run lint
npm test
```
