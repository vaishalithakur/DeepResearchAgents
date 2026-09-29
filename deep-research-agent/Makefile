.PHONY: backend-install backend-dev backend-test backend-lint backend-typecheck \
        frontend-install frontend-dev frontend-build \
        docker-up docker-down

backend-install:
	cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt

backend-dev:
	cd backend && . .venv/bin/activate && uvicorn app.main:app --reload --port 8000

backend-test:
	cd backend && . .venv/bin/activate && pytest

backend-lint:
	cd backend && . .venv/bin/activate && ruff check . && ruff format --check .

backend-typecheck:
	cd backend && . .venv/bin/activate && mypy app

frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

docker-up:
	docker compose up --build

docker-down:
	docker compose down
