### HELP

.PHONY: help
help: ## Print help
	@egrep "(^### |^\S+:.*##\s)" Makefile | sed 's/^###\s*//' | sed 's/^\(\S*\)\:.*##\s*\(.*\)/  \1 - \2/'

### DOCKER

.PHONY: run
run: image ## docker run ...
	(docker stop linux-insides-book 2>&1) > /dev/null || true
	docker run --detach -p 4000:4000 --name linux-insides-book --hostname linux-insides-book linux-insides-book 

.PHONY: start
start: ## start the docker container ...
	docker start linux-insides-book

.PHONY: image
image: ## docker image build ...
	docker image build --rm --squash --label linux-insides --tag linux-insides-book:latest -f Dockerfile . 2> /dev/null || \
	docker image build --rm --label linux-insides --tag linux-insides-book:latest -f Dockerfile . 

.PHONY: sh
sh: ## run interactive shell inside an already running docker container ...
	docker exec -it linux-insides-book bash

.PHONY: rm
rm: ## remove the docker container ...
	(docker stop linux-insides-book 2>&1) > /dev/null || true
	(docker rm linux-insides-book 2>&1) > /dev/null || true

.PHONY: logs
logs: ## gather logs from the docker container ...
	docker logs linux-insides-book

.PHONY: export
export: ## run e-book generation inside an already running docker container ...
	docker exec linux-insides-book /bin/bash -c ' \
	find . -type f -name '*.svg' -a ! \( -path "./.github/*" -o -path "./_book/*" \) -print0 | while IFS= read -r -d "" svg_file; do \
    output_file="$${svg_file%.svg}.png"; \
    chapter_dir=$$(dirname $$(dirname "$$svg_file")); \
    svg_relative_path="$${svg_file#$$chapter_dir/}"; \
    output_relative_path="$${output_file#$$chapter_dir/}"; \
    inkscape --export-png="$$output_file" \
             --export-area-page \
             --export-dpi=150 \
             "$$svg_file"; \
    find "$$chapter_dir" -maxdepth 1 -type f -name "*.md" -print0 | xargs -0 sed -i "s|\\([/ \\t\\(]\\)$${svg_relative_path}|\\1$${output_relative_path}|g"; \
	done; \
	gitbook epub; \
	gitbook mobi; \
	gitbook pdf; \
	mv book.pdf book-A4.pdf; \
	mv book-A5.json book.json; \
	gitbook pdf; \
	mv book.pdf book-A5.pdf; \
	mv book-A4.pdf book.pdf'

.PHONY: cp
cp: ## copy all exported e-book formats to current working directory ...
	docker cp linux-insides-book:/srv/gitbook/book.epub "Linux Inside - 0xAX.epub"
	docker cp linux-insides-book:/srv/gitbook/book.mobi "Linux Inside - 0xAX.mobi"
	docker cp linux-insides-book:/srv/gitbook/book.pdf "Linux Inside - 0xAX.pdf"
	docker cp linux-insides-book:/srv/gitbook/book-A5.pdf "Linux Inside - 0xAX (A5).pdf"

.PHONY: clean
clean: ## remove all exported e-book files ...
	rm "Linux Inside - 0xAX.epub" \
		 "Linux Inside - 0xAX.mobi" \
		 "Linux Inside - 0xAX.pdf" \
		 "Linux Inside - 0xAX (A5).pdf"

### LAUNCH BROWSER

.PHONY: browse
browse: ## Launch broweser
	@timeout 60 sh -c 'until nc -z 127.0.0.1 4000; do sleep 1; done' || true
	@(uname | grep Darwin > /dev/null) && open http://127.0.0.1:4000 || true
	@(uname | grep Linux > /dev/null) && xdg-open http://127.0.0.1:4000 || true
