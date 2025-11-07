.PHONY: help up down build logs ps clean test

help:
	@echo "OpsConductor NMS - Make Commands"
	@echo ""
	@echo "  make up      - Start all services"
	@echo "  make down    - Stop all services"
	@echo "  make build   - Build all services"
	@echo "  make logs    - View logs"
	@echo "  make ps      - List running services"
	@echo "  make clean   - Stop and remove volumes"
	@echo "  make test    - Run tests (TBD)"

up:
	docker compose up -d

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

ps:
	docker compose ps

clean:
	docker compose down -v

test:
	@echo "Running smoke tests..."
	cd tests && pip install -q -r requirements.txt && pytest -v test_smoke.py
