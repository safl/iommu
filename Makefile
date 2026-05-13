PKG := $(notdir $(shell find src -mindepth 1 -maxdepth 1 -type d -not -name '*.egg-info'))

.PHONY: default install format test build clean bump

default:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  install                Install via pipx (editable)"
	@echo "  format                 Run pre-commit hooks on all files"
	@echo "  test                   Run pytest in isolated pipx environment"
	@echo "  build                  Build sdist and wheel"
	@echo "  clean                  Remove build artifacts"
	@echo "  bump NEW_VERSION=x.y.z Update version"

install:
	pipx install -e . --force
	pipx run pre-commit install

format:
	pipx run pre-commit run --all-files

test:
	pipx run --no-cache --spec ".[dev]" pytest tests/ -v

build:
	pipx run build

clean:
	rm -rf dist/ build/ src/*.egg-info

bump:
ifndef NEW_VERSION
	$(error Usage: make bump NEW_VERSION=x.y.z)
endif
	sed -i 's/^__version__ = .*/__version__ = "$(NEW_VERSION)"/' src/$(PKG)/__init__.py
	@echo "Bumped to $(NEW_VERSION)"
