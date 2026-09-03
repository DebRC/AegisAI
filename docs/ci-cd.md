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
- [ ] 17.2 Backend and frontend continuous integration
- [ ] 17.3 Compose image and migration validation
- [ ] 17.4 Release artifact and deployment safeguards
- [ ] 17.5 Workflow verification and operating guide
