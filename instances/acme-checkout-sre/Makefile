# Makefile — Standard build targets for the Acme Checkout SRE intelligent-staff instance
# Delegates to the ./de CLI; see ../../scaffold/de --help for details

.PHONY: help build rebuild validate verify upgrade status diff clean start serve doctor

help:
	@echo "intelligent-staff Instance: acme-checkout-sre"
	@echo "=============================="
	@echo ""
	@echo "Build targets:"
	@echo "  make build       — validate, build, doctor, status"
	@echo "  make rebuild     — clean + build"
	@echo "  make validate    — schema + VERSION validation"
	@echo "  make verify      — validate + build (for CI)"
	@echo "  make upgrade     — check for base scaffold upgrades"
	@echo "  make status      — show build summary"
	@echo "  make diff        — detect runtime drift"
	@echo "  make clean       — erase runtime/"
	@echo ""
	@echo "Runtime targets:"
	@echo "  make start       — launch Claude Code in runtime/"
	@echo "  make serve       — launch bridge (if enabled)"
	@echo "  make doctor      — environment checks"
	@echo ""

build:
	../../scaffold/de validate .
	../../scaffold/de build --force --install-deps
	../../scaffold/de doctor .
	../../scaffold/de status .

rebuild: clean build

validate:
	../../scaffold/de validate .

verify: validate build

upgrade:
	../../scaffold/de upgrade

status:
	../../scaffold/de status .

diff:
	../../scaffold/de diff .

clean:
	../../scaffold/de clean

start:
	../../scaffold/de start

serve:
	../../scaffold/de serve

doctor:
	../../scaffold/de doctor .

# Local hooks: define PRE_BUILD, POST_BUILD, PRE_VERIFY, POST_VERIFY in Makefile.local if needed
-include Makefile.local
