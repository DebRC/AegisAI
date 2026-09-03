# Kubernetes deployment

Phase 18 provides an operator-ready Kubernetes deployment package. It is a
repeatable deployment baseline, not a claim that this repository has been
deployed to a particular cloud account or cluster.

## What it delivers

- Kubernetes manifests for PostgreSQL, Redis, Qdrant, document storage, the
  FastAPI API, Celery worker, Celery Beat, and the Next.js frontend.
- A production overlay using immutable image-tag placeholders. Operators must
  substitute their registry and an actual immutable release tag before apply.
- A separate migration Job. Database migrations finish before application
  workload rollout; application replicas never run migrations themselves.
- Non-root API/worker containers, resource requests and limits, readiness,
  liveness, and startup probes, rolling updates, disruption budgets, and
  CPU-based horizontal autoscaling for API and frontend deployments.
- A secret handoff that keeps database passwords, JWT/SSO/OpenAI credentials,
  and Qdrant credentials out of Git.

## Runtime topology

```text
Internet
   │ optional TLS ingress (frontend only)
   ▼
Next.js frontend ───────────────► FastAPI backend ───► PostgreSQL
      2–6 replicas                  2–6 replicas         1 StatefulSet
                                         │
                                         ├──────────────► Redis
                                         ├──────────────► Qdrant StatefulSet
                                         └──────────────► shared RWX document PVC
                                                               ▲
Celery Beat ──► Redis ──► Celery workers (2 replicas) ────────┘
```

PostgreSQL remains authoritative for business data and the processing outbox.
Redis is only the Celery transport/result channel, so it is intentionally
ephemeral in this baseline. Qdrant holds derived vectors and can be rebuilt
from PostgreSQL chunks and the original documents when necessary.

The shared document PVC is the important storage constraint: both API pods and
worker pods read/write the same original files. Its storage class therefore
must support `ReadWriteMany` across cluster nodes. PostgreSQL and Qdrant each
use their own `ReadWriteOnce` StatefulSet volume.

## Files and safe configuration boundary

| Path | Purpose |
| --- | --- |
| `infrastructure/kubernetes/base/` | Generic Kubernetes resources and a renderable platform/application baseline; migrations stay separate by design. |
| `infrastructure/kubernetes/overlays/production/platform/` | Namespace, configuration, persistent storage, and stateful dependencies. |
| `infrastructure/kubernetes/overlays/production/migration/` | One-time Alembic migration Job. |
| `infrastructure/kubernetes/overlays/production/application/` | API, workers, frontend, autoscaling, and disruption budgets. |
| `infrastructure/kubernetes/overlays/production/secrets.env.example` | Required secret keys and no real secrets. Copy locally; it is ignored by Git. |
| `infrastructure/kubernetes/examples/ingress.yaml` | Optional ingress starting point, deliberately not auto-applied. |

The production Kustomizations use `ghcr.io/debrc/aegisai-*` and
`replace-with-immutable-image-tag` only as safe placeholders. Change both
`newName` values if another registry is used, and change every `newTag` to the
same built-and-pushed immutable image tag or digest. Do not use `latest`.

Before production deployment, update the public callback and frontend URLs in
`base/platform/configmap.yaml` (or provide a production-specific ConfigMap
patch). Enable `SSO_ENABLED` only when the corresponding secret values are set,
then register those exact HTTPS callback URLs with each enabled SSO provider.

## Prerequisites

- A Kubernetes cluster with a default `ReadWriteOnce` storage class and an
  explicit or default **ReadWriteMany** storage class for `document-storage`.
- `kubectl` with Kustomize support, permission to create the `aegisai`
  namespace and its resources, and a cluster metrics API for the HPAs.
- A container registry containing backend and frontend images built from the
  same commit/tag.
- Real production values for the ignored `secrets.env` file.
- An ingress controller, DNS record, and TLS secret only when exposing the web
  application publicly.

This baseline is intentionally a single-replica in-cluster PostgreSQL and
Qdrant deployment. It is suitable as an application deployment reference and
for a small installation. A production service with high availability, backup
and restore objectives, or multi-zone recovery should use the organization’s
managed PostgreSQL/vector platform or replace these StatefulSets with an
approved, separately operated data service before go-live.

## Deploy in the required order

Commands are shown from the repository root. Set the release tag once and
edit both production Kustomization files to use it before deployment.

```bash
# 1. Create your local secret source. This remains untracked.
cp infrastructure/kubernetes/overlays/production/secrets.env.example \
  infrastructure/kubernetes/overlays/production/secrets.env

# 2. Replace every placeholder in secrets.env. URL-encode the password in
#    DATABASE_URL when it contains URL-reserved characters.

# 3. Create or update the Kubernetes Secret without printing it.
kubectl create namespace aegisai --dry-run=client -o yaml | kubectl apply -f -
kubectl -n aegisai create secret generic aegisai-secrets \
  --from-env-file=infrastructure/kubernetes/overlays/production/secrets.env \
  --dry-run=client -o yaml | kubectl apply -f -

# 4. Bring up storage and stateful dependencies first.
kubectl apply -k infrastructure/kubernetes/overlays/production/platform
kubectl -n aegisai rollout status statefulset/postgres --timeout=5m
kubectl -n aegisai rollout status deployment/redis --timeout=5m
kubectl -n aegisai rollout status statefulset/qdrant --timeout=5m

# 5. Run and require the one-time migration to complete.
kubectl -n aegisai delete job aegisai-migrate --ignore-not-found
kubectl apply -k infrastructure/kubernetes/overlays/production/migration
kubectl -n aegisai wait --for=condition=complete job/aegisai-migrate --timeout=10m

# 6. Roll out the stateless application workloads.
kubectl apply -k infrastructure/kubernetes/overlays/production/application
kubectl -n aegisai rollout status deployment/backend --timeout=10m
kubectl -n aegisai rollout status deployment/celery-worker --timeout=10m
kubectl -n aegisai rollout status deployment/celery-beat --timeout=10m
kubectl -n aegisai rollout status deployment/frontend --timeout=10m
```

The namespace command is idempotent. The migration Job is explicitly deleted
before a new release because a Kubernetes Job's pod template is immutable;
deleting only the completed Job does not delete database data or document
files. Never delete the StatefulSet PVCs as part of an application rollback.

After the application is healthy, adapt and apply
`infrastructure/kubernetes/examples/ingress.yaml` only after replacing its
ingress class, hostname, TLS secret, and any organization-required annotations.
The backend is intentionally not public in the example: the frontend calls it
through the internal `backend` service.

## Verify a deployment

```bash
kubectl -n aegisai get pods,svc,pvc,hpa,pdb
kubectl -n aegisai get events --sort-by=.lastTimestamp
kubectl -n aegisai logs deployment/backend --tail=100
kubectl -n aegisai logs deployment/celery-worker --tail=100

# Check application readiness through an internal port-forward.
kubectl -n aegisai port-forward service/backend 8000:8000
# In a second terminal:
curl --fail-with-body http://localhost:8000/health/ready
curl --fail-with-body http://localhost:8000/health/metrics
```

Then sign in through the frontend, upload a small supported document, wait for
its processing job to succeed, run retrieval, and ask a grounded chat question.
This exercises the shared document volume, Redis/Celery delivery, PostgreSQL,
Qdrant, and the application path together.

## Rollback and operations

For an application-only rollback, set the previous known-good immutable tag in
the two production Kustomizations, re-run the migration job only when the
schema is backward-compatible, apply the application overlay, and wait for
both backend and frontend rollouts. Do not roll a database schema backward by
default; review the Alembic revision and restore plan first.

`/health` is a liveness signal. `/health/ready` additionally checks PostgreSQL,
Redis, and Qdrant and keeps unready API pods out of service endpoints. The
startup probe gives those dependencies time to become available without the
liveness probe repeatedly killing a still-starting API process. HPA requires a
metrics API; if the cluster does not provide one, the API and frontend remain
at their requested replica counts and the HPA will report an event.

Use the Phase 16 metrics/logging contract for observability and Phase 17 CI to
render the base and every production deployment stage on every source change.
Network policies, managed-data-service integration, backup scheduling, image
publication, DNS, TLS issuance, and deployment automation are cluster and
organization-specific controls; configure them before public production use.
