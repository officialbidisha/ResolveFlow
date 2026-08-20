# ResolveFlow frontend

React + TypeScript UI for [ResolveFlow](../README.md), talking to the FastAPI
backend in `../app/main.py`.

## Running

```bash
npm install
npm run dev              # http://localhost:5173, expects the backend at localhost:8000
```

Set `VITE_API_URL` (see `.env.production`) to point at a different backend —
`.env.local` overrides it for local development.

## Building

```bash
npm run build
```
