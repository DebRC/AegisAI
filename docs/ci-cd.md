# CI/CD design

## Purpose

Phase 17 turns the local quality gates into repeatable automation. A change is
not considered releasable merely because it builds on one developer machine:
the same backend tests, migration validation, image build, and frontend checks
must run from a clean GitHub-hosted environment.

This phase establishes delivery confidence. It does not silently deploy to an
environment, create cloud infrastructure, or use production credentials. Those
actions need an approved deployment target and are deliberately deferred to
Phase 18.

## 17.1 Delivery contract and trust boundaries

### Required checks for every pull request and protected-branch push

| Check | What it proves | Secrets required |
| --- | --- | --- |
| Backend unit suite | Service, authorization, document, retrieval, chat, audit, and observability boundaries remain correct. | None; test-only settings. |
| Alembic SQL validation | The full migration chain can be generated against PostgreSQL semantics. | None. |
| Backend image build | The Dockerfile's embedded test and migration gates work from a clean image. | None. |
| Frontend type check and production build | The browser application remains type-safe and can produce its production bundle. | None. |
| Compose configuration validation | The declared local platform is structurally valid. | None. |

The workflow must not call OpenAI, an OAuth provider, a live database, or any
other external account. Tests use mocks and CI-only configuration so a pull
request cannot spend API credits or expose a secret.

### Secrets and deployment authority

- Repository secrets are never echoed, written to artifacts, or passed to pull
  request workflows from forks.
- `OPENAI_API_KEY`, SSO client secrets, JWT signing keys, and production
  database URLs are prohibited from ordinary CI.
- A future deployment workflow may run only through an explicit manual release
  approval and an environment protected in the source-control provider.
- Phase 18 will define the deployment target, runtime secrets, rollout,
  rollback, and Kubernetes-specific checks before any automatic deployment is
  enabled.

### Version and artifact policy

CI validates source and container construction now. A later release workflow
will publish immutable image tags derived from an approved Git commit; moving
tags such as `latest` are not deployment authority. The commit SHA remains the
traceable source identity for every build.

### Recommended branch protection

After the workflow is pushed to the remote repository, an administrator should
require its named checks before merging to the protected branch, block force
pushes, and require review for workflow-file changes. This is a source-control
setting, not something the repository can enable by itself.

## Delivery checkpoints

- [x] 17.1 Delivery contract and trust boundaries
- [x] 17.2 Backend and frontend continuous integration
- [x] 17.3 Compose image and migration validation
- [x] 17.4 Release candidate and deployment safeguards
- [x] 17.5 Workflow verification and operating guide

## 17.2 Continuous integration

`.github/workflows/ci.yml` runs for every push and pull request with read-only
repository permission. It uses CI-only environment values, installs locked
dependencies, runs the backend unit suite and offline Alembic SQL validation,
then type-checks, tests, and produces the frontend bundle. It has no checkout
of deployment secrets and no publish or deployment step.

The workflow uses the official setup actions' built-in dependency caches for
pip and npm. Newer commits on the same branch cancel superseded in-progress
CI runs, which avoids spending runner time on obsolete results.

The frontend runs `tsc --noEmit` as its explicit type gate. Next's production
build uses its compiler-API mode because the project-local TypeScript CLI can
finish `--showConfig` before Next attaches its output listener. This avoids a
false build failure while preserving independent type checking in CI.

## 17.3 Compose construction gate

The `compose` CI job runs only after the source-level backend and frontend
checks pass. It validates `docker-compose.yaml` and then builds the backend and
frontend images from a clean GitHub-hosted runner. The backend Dockerfile
already embeds the unit-test and Alembic SQL gates, so this independently proves
that the container recipe—not just a local virtual environment—remains valid.

Because `backend/.env` is intentionally untracked, the job creates it only
inside the ephemeral runner from `backend/.env.example`. This enables Compose
to resolve its declared local service configuration without accessing a real
credential or changing the repository.

The job builds images but never starts the Compose platform. That prevents CI
from creating documents, contacting configured AI/SSO providers, or turning a
pull request into an integration deployment.

## 17.4 Manual release-candidate validation

`release-validation.yml` is deliberately manual. An operator supplies an
existing semantic-version Git tag such as `v1.2.3`; the workflow checks out
that immutable reference, resolves its commit SHA, and builds candidate backend
and frontend images identified by that SHA. Its run summary records the tag,
commit, and candidate image identities for a release handoff.

It has read-only repository access and does **not** publish images, use
repository secrets, deploy an environment, or mutate the Git tag. A registry,
deployment environment, approval policy, rollout, and rollback design are
prerequisites for a later Phase 18 deployment workflow.

## 17.5 Verification and operator setup

### Local verification

```bash
# Validate the local platform declaration and cleanly build its two application images.
docker compose config --quiet
docker compose build --pull backend frontend

# Run the same source-level checks as CI.
cd backend
venv/bin/python -m unittest discover -s tests -v
venv/bin/alembic upgrade head --sql > /tmp/aegis-ci-migrations.sql

cd ../frontend
npm ci
npm run typecheck
npm test
npm run build
```

### GitHub setup and verification

1. Push the commits containing `.github/workflows/ci.yml` to the remote
   repository, then open a pull request or inspect the resulting push run in
   the **Actions** tab.
2. Confirm these three checks succeed: **Backend tests and migration
   validation**, **Frontend type, test, and production build**, and **Compose
   image and migration gates**.
3. In repository branch-protection settings, require all three checks before a
   protected-branch merge and require review for workflow-file changes.
4. To prepare a release candidate, create and push an approved semantic-version
   Git tag, then choose **Release candidate validation** in the Actions tab and
   enter that exact tag. Read the resulting job summary; it is a handoff record,
   not a deployment.

GitHub validates workflow syntax and executes these jobs only after the files
are pushed. The local commands above verify the application behavior and Docker
construction without requiring a remote account or a production secret.
