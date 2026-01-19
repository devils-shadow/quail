.PHONY: venv lint format test run css-bundle css-bundle-restart

CSS_PARTIALS = \
	quail/templates/partials/styles/01-theme.css \
	quail/templates/partials/styles/02-shell.css \
	quail/templates/partials/styles/03-page.css \
	quail/templates/partials/styles/04-admin-components.css \
	quail/templates/partials/styles/05-inbox-message.css \
	quail/templates/partials/styles/06-responsive.css

venv:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt

lint:
	.venv/bin/ruff .

format:
	.venv/bin/black .

test: css-bundle
	.venv/bin/pytest

run:
	.venv/bin/uvicorn quail.web:app --reload

quail/static/quail.css: $(CSS_PARTIALS)
	cat $(CSS_PARTIALS) > quail/static/quail.css

css-bundle: quail/static/quail.css

css-bundle-restart: css-bundle
	sudo systemctl restart quail
