.PHONY: run install update-ytdlp docker-up docker-down check

install:
	python3 -m venv .venv
	.venv/bin/pip install -U pip
	.venv/bin/pip install -r requirements.txt

run:
	.venv/bin/python main.py

update-ytdlp:
	.venv/bin/pip install -U yt-dlp

check:
	.venv/bin/python -m py_compile main.py config.py cogs/*.py utils/*.py

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down
