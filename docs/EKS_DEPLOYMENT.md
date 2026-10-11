# EKS deployment (learning environment)

Status: **non-production, additive.** Render (API), Vercel (frontend), Pinecone, OpenAI and
GitHub OAuth are unchanged. Nothing here runs from `.github/workflows`.

## What was actually verified

| Item | Where | Evidence |
|---|---|---|
| Hardened image (`deploy/Dockerfile.k8s`): non-root UID 10001, no `.env`/frontend/docs in image, exec-form `CMD` | local Docker | `id -u` = 10001; `/app/.env` absent |
| Deployment (`deploy/k8s/app.yaml`): 2 replicas, startup/readiness/liveness probes, `preStop`, memory limit, `maxUnavailable: 0` | local Kubernetes (Docker Desktop) | rollout succeeded; both pods served `/api/health` |
| Failed rollout keeps old pods serving, `kubectl rollout undo` restores | local Kubernetes | bad image -> `ErrImageNeverPull`, old pods stayed Ready |
| 401 on `/api/auth/me` and on resume with a forged cookie | local Kubernetes | HTTP codes |
| Exactly-once GitHub writes (`docs/exactly-once/`) | local Postgres | `demo.py`: 5 racing callers -> 1 comment |
| EKS control plane in `ap-southeast-2` | AWS | cluster `ACTIVE`, v1.35 |

## Designed, not deployed

ALB + ACM + WAF ingress, Secrets Manager (CSI), EKS Pod Identity, GitHub OIDC CI
(`deploy/aws/ci-eks.yml.example`, `github-oidc-trust.json`), HPA, PodDisruptionBudget, NetworkPolicy,
image signing/admission control, Bedrock / S3 Vectors retrieval, LLM gateway.

## Problems hit and what they taught

1. **Org SCP region lock**: EKS/ECR/EC2 denied in `us-east-1`, allowed in `ap-southeast-2`. Read the
   explicit-deny message, probed regions, moved the cluster. Did not attempt to bypass the guardrail.
2. **Org SCP on IAM OIDC providers**: `eksctl` failed at "associate IAM OIDC provider". IRSA is
   unavailable here; the design uses EKS Pod Identity. Add-ons were created via the EKS API instead.
3. **Free Plan instance restriction**: managed nodegroup sat in `CREATING` for 21 min with empty health
   issues. Root cause was in the Auto Scaling group activity log: instance type not free-tier
   eligible. Debug path: nodegroup health -> CloudFormation events -> EC2 -> ASG activities.
4. **Own bug**: the push script built the Sydney registry URL but let the CLI pick its default
   region. Fixed by exporting one explicit region.

## Known app risks this exposed (not yet fixed in app code)

- Concurrent/replayed resume can post a GitHub comment twice -> design in `docs/exactly-once/`.
- GitHub OAuth token is stored in plaintext in `sessions` and inside LangGraph checkpoints.
- Every replica runs schema setup at boot (needs a migration Job or advisory lock).
- `tools/retrieval.py` calls Pinecone at import time, so a Pinecone outage crash-loops pods.
- `/api/health` does not check Postgres; readiness and liveness should be separate.

## Commands

```bash
# local
docker build -f deploy/Dockerfile.k8s -t resolveflow:v1 .
kubectl apply -f deploy/k8s/postgres.yaml        # throwaway DB, local only
kubectl -n resolveflow create secret generic resolveflow-secrets ...   # from your shell; never commit
kubectl apply -f deploy/k8s/app.yaml

# aws (chargeable: ~$0.10/h control plane + nodes + NAT)
eksctl create cluster -f deploy/aws/cluster.yaml --profile <profile> ...
AWS_PROFILE=<profile> deploy/aws/ecr-push.sh
eksctl delete cluster --name resolveflow-test --region ap-southeast-2   # teardown
```
