# Makefile — Standard build targets for a DE instance
# Managed file: do not hand-edit. Scaffold upgrades may update it.

.PHONY: help build rebuild validate verify upgrade status diff clean start serve

help:
	@echo "DE instance targets:"
	@echo "  make build       — validate, build, doctor, status"
	@echo "  make rebuild     — clean + build"
	@echo "  make validate    — schema + VERSION validation"
	@echo "  make verify      — run smoke tests"
	@echo "  make upgrade     — check for base scaffold upgrades"
	@echo "  make status      — show build summary"
	@echo "  make diff        — detect runtime drift"
	@echo "  make clean       — erase runtime/"
	@echo "  make start       — launch Claude Code in runtime/"
	@echo "  make serve       — launch bridge (if enabled)"

build:
	./de validate
	./de build --force --install-deps
	./de doctor
	./de status

rebuild: clean build

validate:
	./de validate

verify:
	./de validate && ./de build --force --install-deps

upgrade:
	./de upgrade

status:
	./de status

diff:
	./de diff

clean:
	./de clean

start:
	./de start

serve:
	./de serve

# Local hooks: define PRE_BUILD, POST_BUILD, PRE_VERIFY, POST_VERIFY in Makefile.local if needed
-include Makefile.local
