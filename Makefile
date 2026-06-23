.DEFAULT_GOAL := help
SHELL := /usr/bin/env bash

COMPOSE_DEV := docker compose -f compose.dev.yml
COMPOSE_PROD := docker compose -f compose.prod.yml

# Used by deploy target. Override with `make deploy TAG=<sha>`.
TAG ?= main

# ---------------------------------------------------------------------------
.PHONY: help
help:  ## Show available targets
	@awk 'BEGIN { FS = ":.*?## " } /^[a-zA-Z_%-]+:.*?## / { printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

# ---- Dev --------------------------------------------------------------------
.PHONY: dev dev-down logs ps
dev:  ## Start dev stack (postgres, redis, api, worker, web) with hot reload
	@[[ -f .env ]] || cp .env.example .env
	$(COMPOSE_DEV) up --build

dev-down:  ## Stop and remove dev containers (keeps volumes)
	$(COMPOSE_DEV) down

logs:  ## Tail logs (set S=api|worker|web|postgres|redis to filter)
	$(COMPOSE_DEV) logs -f $(S)

ps:  ## List dev containers
	$(COMPOSE_DEV) ps

# ---- Shells -----------------------------------------------------------------
.PHONY: shell-api shell-worker shell-db redis-cli
shell-api:  ## Open a shell in the api container
	$(COMPOSE_DEV) exec api bash

shell-worker:  ## Open a shell in the worker container
	$(COMPOSE_DEV) exec worker bash

shell-db:  ## Open psql in the postgres container
	$(COMPOSE_DEV) exec postgres psql -U $$(grep ^POSTGRES_USER .env | cut -d= -f2) -d $$(grep ^POSTGRES_DB .env | cut -d= -f2)

redis-cli:  ## Open redis-cli
	$(COMPOSE_DEV) exec redis redis-cli

# ---- Migrations -------------------------------------------------------------
.PHONY: migrate migrate-new migrate-down
migrate:  ## Apply DB migrations
	$(COMPOSE_DEV) exec api alembic upgrade head

migrate-new:  ## Generate a new migration (M="add foo")
	@if [[ -z "$(M)" ]]; then echo 'Usage: make migrate-new M="my message"'; exit 1; fi
	$(COMPOSE_DEV) exec api alembic revision --autogenerate -m "$(M)"

migrate-down:  ## Roll back one migration
	$(COMPOSE_DEV) exec api alembic downgrade -1

# ---- Quality ----------------------------------------------------------------
.PHONY: lint format typecheck test ci
lint:  ## Run linters across all apps
	cd apps/api && uv run ruff check . && uv run ruff format --check .
	cd apps/worker && uv run ruff check . && uv run ruff format --check .
	cd apps/web && npm run lint

format:  ## Auto-format all code
	cd apps/api && uv run ruff format . && uv run ruff check --fix .
	cd apps/worker && uv run ruff format . && uv run ruff check --fix .
	cd apps/web && npm run format

typecheck:  ## Run type checkers
	cd apps/api && uv run mypy src
	cd apps/worker && uv run mypy src
	cd apps/web && npm run typecheck

test:  ## Run all tests
	cd apps/api && uv run pytest

ci: lint typecheck test  ## Everything CI does

# ---- Deploy -----------------------------------------------------------------
.PHONY: deploy rollback kill
deploy:  ## Trigger deploy workflow (TAG=<sha|main|tag>, default: main)
	gh workflow run deploy.yml -f image_tag=$(TAG)
	@echo "Watching at: $$(gh repo view --json url -q .url)/actions"

rollback:  ## Roll back to previous image tag (run on VPS)
	@echo "SSH to VPS and run: cd /opt/maelstrom && ./infra/scripts/rollback.sh"

kill:  ## Print kill-switch instructions
	@echo "SSH to VPS and run: cd /opt/maelstrom && ./infra/scripts/kill-switch.sh"

# ---- Misc -------------------------------------------------------------------
.PHONY: clean
clean:  ## Remove build artifacts and caches
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
	find . -type d -name .ruff_cache -prune -exec rm -rf {} +
	find . -type d -name .mypy_cache -prune -exec rm -rf {} +
	find . -type d -name .next -prune -exec rm -rf {} +
