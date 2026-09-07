.PHONY: run test backup restore

run:
	./scripts/run-demo.sh

test:
	uv run pytest

backup:
	./scripts/backup.sh

restore:
	@test -n "$(BACKUP)" || (echo "Usage: make restore BACKUP=/path/to/file.wpbackup" && exit 2)
	./scripts/restore.sh "$(BACKUP)"
