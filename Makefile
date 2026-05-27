.PHONY: install run test init-db docker-up docker-down

install:
	python -m pip install -r requirements.txt

run:
	uvicorn main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest

init-db:
	python scripts/init_db.py

docker-up:
	docker compose up --build

docker-down:
	docker compose down
