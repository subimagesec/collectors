COLLECTORS := $(sort $(patsubst %/Makefile,%,$(wildcard */Makefile)))

.PHONY: test test_lint test_unit

test test_lint test_unit:
	@set -e; for collector in $(COLLECTORS); do \
		$(MAKE) -C "$$collector" "$@"; \
	done
