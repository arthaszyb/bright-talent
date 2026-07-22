# Repo-level developer entry points. Every target is what CI runs, verbatim.
# Component-level targets live in instances/*/Makefile.

.PHONY: help lint leak-check test test-builder test-bridge test-console test-eval test-mocks build demo

help:
	@echo "make lint        - ruff over the whole repo"
	@echo "make leak-check  - fictional-universe red-line scan"
	@echo "make test        - all component test suites"
	@echo "make build       - validate + build the reference instance"
	@echo "make demo        - one command: build, mock Change Gateway (:8801) + governance console (:8900)"

lint:
	uvx ruff check .

leak-check:
	bash scripts/leak-check.sh .

test: test-builder test-bridge test-console test-eval test-mocks

test-builder:
	uv run --project scaffold/builder --extra dev pytest scaffold/builder/tests -q

test-bridge:
	uv run --project bridge --extra dev pytest bridge/tests -q

test-console:
	uv run --project console --extra dev pytest console/tests -q

test-eval:
	uv run --project eval --extra dev pytest eval/tests -q

test-mocks:
	uv run --project mocks --extra dev pytest mocks/tests -q

build:
	cd instances/acme-checkout-sre && ../../scaffold/de validate . && ../../scaffold/de build .

# One-command demo: mock gateway + governance console against this repo.
# (The interactive DE session itself needs an authenticated `claude` CLI:
#  cd instances/acme-checkout-sre && ../../scaffold/de start .)
demo: build
	@echo ""
	@echo "  Change Gateway  → http://localhost:8801/tickets/1001"
	@echo "  Governance UI   → http://localhost:8900"
	@echo "  Ctrl-C stops both."
	@echo ""
	@trap 'kill 0' EXIT INT TERM; \
	uv run python mocks/change_gateway.py --port 8801 & \
	uv run --project console python -m console.app --repo . --port 8900
