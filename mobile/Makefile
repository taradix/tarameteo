NODE_MODULES := node_modules

NODE := npm exec -- node
TOUCH := $(NODE) -e 'fs.utimesSync(process.argv[1], new Date(), new Date())'

$(NODE_MODULES):
	@echo Installing Node environment
	@npm install
	@$(TOUCH) $@

.PHONY: setup
setup: $(NODE_MODULES)

.PHONY: check
check: $(NODE_MODULES)
	@npm run lint
	@npm run typecheck
	@npx expo install --check
	@npm run openapi
	@git diff --exit-code src/api-types.ts

.PHONY: test
test: $(NODE_MODULES)
	@npm run test

.PHONY: coverage
coverage: $(NODE_MODULES)
	@npm run coverage

.DEFAULT_GOAL := test
