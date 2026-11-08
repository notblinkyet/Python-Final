install:
	uv sync

project:
	uv run project

build:
	uv build

publish:
	uv build
	uvx twine check dist/*

package-install:
	uv tool install --force dist/*.whl

lint:
	uv run ruff check .

format:
	uv run ruff format .

.PHONY: install project build publish package-install lint format
