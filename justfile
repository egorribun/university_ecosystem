set shell := ["bash", "-c"]

install:
	make install

backend-test:
	make backend-test

backend-typecheck:
	make backend-typecheck

frontend-test:
	make frontend-test

frontend-build:
	make frontend-build

lint:
	make lint

test:
	make test

backend-serve:
	make backend-serve

frontend-dev:
	make frontend-dev

generate-api:
	make generate-api

alembic-check:
	make alembic-check
