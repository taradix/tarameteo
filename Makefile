ENV := .env
SUBDIRS := backend firmware frontend
TARGETS := setup check test coverage

-include $(ENV)

.PHONY: $(TARGETS) $(SUBDIRS)
$(TARGETS): $(SUBDIRS)
$(SUBDIRS):
	@$(MAKE) -C $@ $(MAKECMDGOALS)

NODE_MODULES := node_modules
TOUCH := node -e "import fs from 'fs'; const f=process.argv[1]; try{fs.utimesSync(f,new Date(),new Date())}catch{fs.closeSync(fs.openSync(f,'w'))}"

package-lock.json: package.json
	@echo "==> Updating lock file..."
	@npm install --package-lock-only

# Build node_modules with deps.
$(NODE_MODULES): package-lock.json
	@echo "==> Installing Node environment..."
	@npm install
	@$(TOUCH) $@

# Convenience target to build node_modules
.PHONY: setup
setup: $(NODE_MODULES)

.PHONY: check
check: $(NODE_MODULES)
	@echo "==> Linting docker compose files..."
	@npm run lint

.PHONY: deploy
deploy:
	@echo "==> Pulling external images..."
	@docker compose pull --quiet
	@echo "==> Building images..."
	@docker compose build --pull
	@echo "==> Stopping and recreating services..."
	@docker compose up --detach --remove-orphans --wait
	@echo "==> Removing dangling images..."
	@docker image prune --force
	@echo "==> Deployment complete!"
	@docker compose ps

.PHONY: undeploy
undeploy:
	@echo "==> Stopping services..."
	@docker compose down
	@echo "==> Services stopped"

.PHONY: clean
clean:
	@echo "==> Cleaning ignored files..."
	@git clean -Xfd

.DEFAULT_GOAL := test
