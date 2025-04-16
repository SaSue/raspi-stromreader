#!/bin/bash

# Gewünschter Git-Branch (default: main)
BRANCH="${1:-main}"
REPO_DIR=~/raspi-stromreader

# Prüfen, ob das Verzeichnis existiert
if [ -d "$REPO_DIR/.git" ]; then
    echo "Wechsle zu bestehendem Repo unter $REPO_DIR"
    cd "$REPO_DIR" || exit 1

    echo "Hole neueste Änderungen von GitHub..."
    git fetch origin
    git checkout "$BRANCH"
    git pull origin "$BRANCH"
else
    echo "Repo nicht vorhanden, klone es neu"
    git clone --branch "$BRANCH" "https://SaSue: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@github.com/SaSue/raspi-stromreader.git" "$REPO_DIR"
    cd "$REPO_DIR" || exit 1
fi

# Dateien ins Webverzeichnis kopieren
cp -v html/*.* /var/www/html

# DEBUG=0 setzen
sed -i 's/DEBUG=1/DEBUG=0/' docker-compose.yml

# Container neu bauen und starten
cd $REPO_DIR/dashboard
echo "Baue Docker-Container neu..."
docker compose build
docker compose up -d

