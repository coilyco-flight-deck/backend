DEFAULT_GOAL := help

.PHONY: deploy

dns-name ?= $(shell cat coily.yaml | yq e '.dns-name')
email ?= $(shell cat coily.yaml | yq e '.email')
name ?= $(shell cat coily.yaml | yq e '.name')
name-dashed ?= $(subst /,-,$(name))
git-hash ?= $(shell git rev-parse HEAD)
# Fully-qualified ref into the in-cluster registry. Forgejo Actions builds
# this, pushes it over plain http (the runner's DinD carries
# --insecure-registry=192.168.0.194:30500), and kai-server's containerd
# pulls it via its registries.yaml insecure entry. See
# coilysiren/infrastructure#168, #171.
image-url ?= 192.168.0.194:30500/$(name-dashed):$(git-hash)

echo:
	echo $(image-url)

help: ## Print this help.
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "%-30s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build-native: ## uv lock + uv sync.
	uv lock
	uv sync

.build-docker:
	docker build \
		--progress plain \
		--build-arg BUILDKIT_INLINE_CACHE=1 \
		--cache-from $(name):latest \
		-t $(name):$(git-hash) \
		-t $(name):latest \
		.

build-docker: .build-docker ## Build the docker image locally with BuildKit cache.

# Apply the k8s manifest. The image roll itself is done by the Forgejo
# Actions deploy job (.forgejo/workflows/build-publish-deploy.yml); this
# target is for applying structural changes to deploy/main.yml.
.deploy:
	env \
		NAME=$(name-dashed) \
		DNS_NAME=$(dns-name) \
		IMAGE=$(image-url) \
		envsubst < deploy/main.yml | kubectl apply -f -
	kubectl rollout status deployment/$(name-dashed)-app -n $(name-dashed) --timeout=5m

deploy: .deploy ## Apply the k8s manifest to the cluster.

run-native: ## Run the FastAPI server with autoreload on port 4000.
	uv run uvicorn backend.main:app --reload --port 4000 --host 0.0.0.0

run-docker: ## Run the published container locally on port 4000.
	docker run --expose 4000 -p 4000:4000 -it --rm $(name):latest

test: ## Run the pytest suite.
	uv run pytest
