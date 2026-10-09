PY=.venv/bin/python
export DATABASE_URL?=postgresql://brambilla:brambilla@127.0.0.1:5433/brambilla
export CRM_TOKEN?=dev-token
export BASE_URL?=http://127.0.0.1:8000

.PHONY: venv server ui build acceptance smoke docker

venv:
	python3.12 -m venv .venv && .venv/bin/pip install -q -r server/requirements.txt -r tests/requirements.txt

server:
	.venv/bin/uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload

ui:
	cd frontend && npm run dev

build:
	cd frontend && npm ci && npm run build

acceptance:
	.venv/bin/pytest -q tests/acceptance

smoke:
	.venv/bin/pytest -q tests/acceptance -k "health or auth or reset"

docker:
	docker build -t brambilla-crm . && docker run --rm -p 8000:8000 -e PORT=8000 -e DATABASE_URL=$(DATABASE_URL) -e CRM_TOKEN=$(CRM_TOKEN) --network host brambilla-crm
