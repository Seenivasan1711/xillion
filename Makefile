.PHONY: install dev-backend dev-frontend lint format type-check test \
        db-init db-upgrade render-build render-start clean

# ── Local development ──────────────────────────────────────────────────────────

install:
	pip install -e ".[dev]"
	npm --prefix frontend install

dev-backend:
	uvicorn xillion.main:app --host 0.0.0.0 --port 8000 --reload

dev-frontend:
	npm --prefix frontend run dev

db-init:
	mkdir -p data
	xillion db upgrade

db-upgrade:
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

# ── Utilities ──────────────────────────────────────────────────────────────────

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	rm -rf frontend/dist frontend/.vite
