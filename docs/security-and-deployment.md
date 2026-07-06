# Payroll Copilot — Security & Deployment

## Security

### Authentication & Authorization

| Mechanism | Details |
|-----------|---------|
| JWT Access Token | 1 hour TTL, RS256 signed |
| Refresh Token | 7 days, rotated on use, stored hashed |
| Guest Token | Opaque token, 24h TTL, payslip upload only |
| API Keys | Per-org keys for n8n/system integrations |
| RBAC | Enforced at use-case layer + DB RLS |

### Role Permissions Matrix

| Resource | Guest | Employee | Accountant | Admin |
|----------|-------|----------|------------|-------|
| Upload own payslip | ✓ | ✓ | ✓ | ✓ |
| Upload bulk PDF | | | ✓ | ✓ |
| View own validation | ✓ | ✓ | ✓ | ✓ |
| View all validations | | | ✓ | ✓ |
| Import employee Excel | | | ✓ | ✓ |
| Approve legal diffs | | | ✓ | ✓ |
| Manage users | | | | ✓ |
| Attendance review | | | ✓ | ✓ |

### Data Protection

- **National ID:** AES-256-GCM encrypted at application layer before DB storage
- **Files:** Server-side encryption (SSE-S3) in object storage; no public access
- **Backups:** Encrypted; separate access controls
- **Logs:** PII scrubbed; national IDs never logged
- **Network:** Internal services on private Docker network; only API exposed

### Input Validation

- Pydantic strict mode on all API inputs
- File upload: max size 50MB (single), 200MB (bulk PDF)
- Magic byte verification (not extension-only)
- PDF JavaScript/action stripping via sanitization pass
- SQL injection: SQLAlchemy parameterized queries only

### Audit

All sensitive operations logged to append-only `audit_logs`:
- Document upload/download
- Validation runs
- Employee data changes
- Legal rule approvals
- Login/logout/failed auth

Retention: 7 years minimum.

---

## Deployment

### Docker Compose Services

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| api | Built | 8000 | FastAPI application |
| worker | Built | — | Celery worker |
| beat | Built | — | Scheduled tasks |
| postgres | pgvector/pgvector:pg16 | 5432 | Database |
| redis | redis:7-alpine | 6379 | Broker + cache |
| minio | minio/minio | 9000 | Object storage |

Optional profile `docker-ollama`:
| ollama | ollama/ollama | 11434 | Docker Ollama fallback (when host Ollama unavailable) |

Optional profile `automation`:
| n8n | n8nio/n8n | 5678 | Email workflows |

### Ollama in Docker

By default, `api` and `worker` connect to **host Ollama** at `http://host.docker.internal:11434`.
Both services include `extra_hosts: host.docker.internal:host-gateway` for Linux.

**Resolution order** (when `OLLAMA_BASE_URL` is empty):

1. Probe `OLLAMA_HOST_URL` (`GET /api/tags`, 2s timeout)
2. If unreachable → use `OLLAMA_DOCKER_URL` (`http://ollama:11434`)

Set `OLLAMA_BASE_URL` explicitly to skip probing. Start the Docker Ollama service only when needed:

```bash
docker compose --profile docker-ollama up -d
```

### Environment Variables

See `.env.example` in project root.

### Production Checklist

- [ ] TLS termination at reverse proxy (nginx/traefik)
- [ ] PostgreSQL managed service with automated backups
- [ ] S3 instead of MinIO
- [ ] Redis managed or persistent volume
- [ ] Secrets in vault (not .env files)
- [ ] RLS policies verified per tenant
- [ ] Rate limiting enabled
- [ ] WAF rules for file upload endpoints
- [ ] Ollama on GPU node or dedicated inference server
- [ ] Monitoring: Prometheus + Grafana or cloud equivalent
- [ ] Log aggregation: ELK or cloud equivalent

### Scaling

| Component | Scale Strategy |
|-----------|----------------|
| API | Horizontal (stateless) |
| Workers | Horizontal by queue depth |
| PostgreSQL | Vertical + read replicas |
| Ollama | Dedicated GPU instances |
| Object storage | Inherent S3 scale |

### CI/CD

```
Lint (ruff) → Type check (mypy) → Unit tests → Integration tests →
Build Docker image → Push to registry → Deploy to staging →
Smoke tests → Deploy to production
```

---

## Backup & Disaster Recovery

| Component | RPO | RTO |
|-----------|-----|-----|
| PostgreSQL | 1 hour | 4 hours |
| Object storage | 0 (versioning) | 1 hour |
| Redis | N/A (ephemeral) | Immediate |

Quarterly restore drills recommended.
