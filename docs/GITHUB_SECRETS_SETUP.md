# GitHub Secrets Setup for Auto-Deploy

ResolveFlow uses GitHub Actions to auto-deploy on every push to `main`. To enable auto-deployments, you need to set up GitHub Secrets.

## Why Secrets?

The deploy workflow needs:
- **Vercel Token** — to deploy frontend
- **Render API Key** — to deploy backend
- **Service IDs** — to identify which services to deploy

These credentials should never be in the code, only in GitHub Secrets.

## Setup Steps

### 1. Get Vercel Token

1. Go to https://vercel.com/account/tokens
2. Click "Create Token"
3. Name it `ResolveFlow-GitHub-Deploy`
4. Copy the token (it's long, starts with `v_...`)

### 2. Get Vercel Org/Project IDs

1. Go to your Vercel project: https://vercel.com/officialbidisha1/resolveflow-web-officialbidishas-projects
2. Open **Settings → General**
3. Find:
   - **Org ID** (under your name at top)
   - **Project ID** (under project name)
4. Copy both

### 3. Get Render API Key

1. Go to https://dashboard.render.com/account/api-tokens
2. Click "Create API Key"
3. Name it `GitHub-Deploy`
4. Copy the key

### 4. Get Render Service ID

1. Go to your Render dashboard: https://dashboard.render.com
2. Click your "resolveflow-api" service
3. Look at the URL or Settings → copy the Service ID
   - Format: `srv-1a2b3c4d5e6f7g8h`

### 5. Add to GitHub Secrets

1. Go to your GitHub repo: https://github.com/officialbidisha/ResolveFlow
2. Click **Settings → Secrets and variables → Actions**
3. Click **New repository secret** for each:

| Secret Name | Value | From |
|---|---|---|
| `VERCEL_TOKEN` | Your Vercel token | Step 1 |
| `VERCEL_ORG_ID` | Your Vercel org ID | Step 2 |
| `VERCEL_PROJECT_ID` | Your Vercel project ID | Step 2 |
| `RENDER_API_KEY` | Your Render API key | Step 3 |
| `RENDER_SERVICE_ID` | Your Render service ID | Step 4 |

**Note:** The workflow checks if secrets exist. If missing, it logs a warning and skips that deploy step.

## Verify Setup

After adding secrets:

1. Go to GitHub **Actions** tab
2. Push a test commit: `git commit --allow-empty -m "test: verify deployment"`
3. Watch the workflow run
4. Check that Vercel and Render deployments succeeded

## Example: Step-by-Step

### Get Vercel Token
```
visit: https://vercel.com/account/tokens
action: Create Token
copy: v_abc123def456...
```

### Get Vercel IDs
```
visit: https://vercel.com/officialbidisha1/resolveflow-web
click: Settings → General
copy: Org ID = OrganizationId123
copy: Project ID = ProjectId456
```

### Get Render Key
```
visit: https://dashboard.render.com/account/api-tokens
action: Create API Key
copy: rnd_abc123def456...
```

### Get Render Service ID
```
visit: https://dashboard.render.com
click: resolveflow-api service
copy: Service ID = srv_1a2b3c4d5e6f7g8h
```

### Add to GitHub
```
visit: https://github.com/officialbidisha/ResolveFlow/settings/secrets/actions
add: VERCEL_TOKEN = v_abc123def456...
add: VERCEL_ORG_ID = OrganizationId123
add: VERCEL_PROJECT_ID = ProjectId456
add: RENDER_API_KEY = rnd_abc123def456...
add: RENDER_SERVICE_ID = srv_1a2b3c4d5e6f7g8h
```

### Test
```
git commit --allow-empty -m "test: verify deployment"
git push origin main
watch: https://github.com/officialbidisha/ResolveFlow/actions
```

## Troubleshooting

### "Secret not found" in logs

The workflow ran but a secret is missing. Add it following the steps above.

### Vercel deploy fails with "permission denied"

Token might be:
- Expired — regenerate at https://vercel.com/account/tokens
- Wrong scope — create new token with "projects" scope
- Wrong account — make sure it's from the right Vercel account

### Render deploy fails with "404"

- Service ID is wrong — copy exact ID from dashboard
- API key is expired — regenerate
- Service name changed — update RENDER_SERVICE_ID

### Nothing deploys (secrets set, but no deploy happens)

1. Check GitHub Actions log: does it show "Skipping deploy"?
2. If yes, a required secret is missing — add it
3. If no, the evals (`eval.harness`) failed — fix those first

## What Gets Deployed

Once secrets are set:

```
Push to main
    ↓
eval.harness runs (12/12 safety gates)
    ↓
If PASSING:
  ├─ vercel deploy → Frontend goes live
  └─ Render API call → Backend redeploys
    ↓
https://resolveflow-web-officialbidishas-projects.vercel.app (updated)
https://resolveflow-1h99.onrender.com/api (updated)
```

## Security Notes

- Secrets are never printed in logs
- Each secret is masked as `***` in output
- Tokens should be long-lived but rotatable
- If a secret leaks, regenerate it immediately
- Don't commit credentials to the repo (GitHub prevents this anyway)

## Need Help?

If deployment still fails after setting secrets:

1. Check the GitHub Actions log for the exact error
2. Verify each secret exists and is correct
3. Try manually deploying via Vercel/Render dashboards to isolate the issue
4. Check that `vercel.json` and `render.yaml` configs are valid

Still stuck? See `docs/DEPLOYMENT.md` for manual deployment steps.
