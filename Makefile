.PHONY: setup install dev dev-backend dev-frontend lint format type-check test \
        db-init db-upgrade render-build render-start docker-build docker-run backup clean

# ── First-time setup ───────────────────────────────────────────────────────────

setup: ## One-time: create .env, install all deps, init DB
	@test -f .env && echo ".env already exists — skipping copy" || (cp .env.example .env && echo "Created .env — review it before going live")
	pip install -e ".[dev]"
	npm --prefix frontend install
	mkdir -p data
	@echo ""
	@echo "Setup complete. Run 'make dev' to start everything."

# ── Local development ──────────────────────────────────────────────────────────

install: ## Install Python + Node deps (re-run after adding packages)
	pip install -e ".[dev]"
	npm --prefix frontend install

dev: ## ★ Start backend + frontend together. Ctrl+C stops both.
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  Xillion starting up"
	@echo "  API  →  http://localhost:8001"
	@echo "  UI   →  http://localhost:5174"
	@echo "  Docs →  http://localhost:8001/api/docs"
	@echo "  Ctrl+C to stop everything"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@mkdir -p data
	@trap 'kill 0' INT TERM EXIT; \
	uvicorn xillion.main:app --host 0.0.0.0 --port 8001 --reload 2>&1 | sed 's/^/[backend] /' & \
	npm --prefix frontend run dev 2>&1 | sed 's/^/[frontend] /' & \
	wait

dev-backend: ## Backend only (uvicorn with --reload)
	uvicorn xillion.main:app --host 0.0.0.0 --port 8001 --reload

dev-frontend: ## Frontend only (Vite dev server)
	npm --prefix frontend run dev

db-init: ## Create data/ and run migrations
	mkdir -p data
	alembic upgrade head

db-upgrade: ## Run pending Alembic migrations
	alembic upgrade head

# ── Code quality ───────────────────────────────────────────────────────────────

lint:
	ruff check .
	black --check .

format:
	ruff check --fix .
	black .

type-check:
	mypy xillion

test:
	pytest tests/ -v --cov=xillion --cov-report=term-missing

test-unit:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v

# ── Render deployment ──────────────────────────────────────────────────────────

render-build:
	node --version
	npm --prefix frontend ci
	npm --prefix frontend run build
	pip install -e ".[prod]"

render-start:
	alembic upgrade head
	uvicorn xillion.main:app --host 0.0.0.0 --port $${PORT:-8000} --workers 2

# ── Docker (production) ────────────────────────────────────────────────────────

docker-build: ## Build production Docker image
	docker build -t xillion:latest .

docker-run: ## Run production image (set PORT, DATABASE_URL, APP_SECRET_KEY in env)
	docker run --rm -p 8000:8000 --env-file .env xillion:latest

# ── Backup ─────────────────────────────────────────────────────────────────────

backup: ## Snapshot SQLite to data/backups/ (keep 30 days)
	./scripts/backup_db.sh

# ── Utilities ──────────────────────────────────────────────────────────────────

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	rm -rf frontend/dist frontend/.vite
