.PHONY: export-deps
export-deps:
	poetry export --without-hashes -f requirements.txt --output requirements.txt

.PHONY: run
run:
	docker compose up --build