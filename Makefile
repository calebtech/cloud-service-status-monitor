.PHONY: venv install test run dry-run seed serve docker-build helm-template

PYTHON ?= python3
VENV ?= .venv
export PYTHONPATH := src

venv:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -r requirements.txt
	$(VENV)/bin/pip install pytest

install: venv

test:
	$(VENV)/bin/python -m pytest -q

run:
	$(VENV)/bin/python -m cloud_status_monitor --config config/config.yaml

dry-run:
	DRY_RUN=true $(VENV)/bin/python -m cloud_status_monitor --config config/config.yaml --dry-run -v

seed:
	$(VENV)/bin/python -m cloud_status_monitor --config config/config.yaml --seed -v

serve:
	$(VENV)/bin/python -m cloud_status_monitor --config config/config.yaml --serve --host 0.0.0.0 --port 8080

docker-build:
	docker build -t cloud-service-status-monitor:local .

helm-template:
	helm template cloud-status ./charts/cloud-service-status-monitor
