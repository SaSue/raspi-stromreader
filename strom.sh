#!/bin/bash

# Gewünschter Git-Branch (default: main)
BRANCH="${1:-main}"
REPO_DIR=~/raspi-stromreader

# Auswahlmenü anzeigen
echo "Bitte wählen Sie eine Option:"
echo "1 = Dashboard bauen"
echo "2 = Reader bauen"
read -rp "Ihre Auswahl: " AUSWAHL

# Prüfen, ob das Verzeichnis existiert
if [ -d "$REPO_DIR/.git" ]; then
    echo "Wechsle zu bestehendem Repo unter $REPO_DIR"
    cd "$REPO_DIR" || exit 1

    echo "Hole neueste Änderungen und setze lokale Änderungen zurück..."

    # Alle lokalen Änderungen verwerfen
    git fetch origin
    git reset --hard origin/"$BRANCH"
    git clean -fd

    git fetch origin
    git checkout "$BRANCH"
    git pull origin "$BRANCH"
else
    echo "Repo nicht vorhanden, klone es neu"
    git clone --branch "$BRANCH" "https://SaSue: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@github.com/SaSue/raspi-stromreader.git" "$REPO_DIR"
    cd "$REPO_DIR" || exit 1
fi

# sh ausführbar machen

chmod +x $REPO_DIR/strom.sh

# Auswahl ausführen
case $AUSWAHL in
    1)
        echo "Dashboard wird gebaut..."
        # Dateien ins Webverzeichnis kopieren
        cp -v html/*.* /var/www/html

        # DEBUG=0 setzen
        sed -i 's/DEBUG=1/DEBUG=0/' docker-compose.yml

        # Container neu bauen und starten
        cd $REPO_DIR/dashboard
        echo "Dashboard wird gebaut..."
        echo "Baue Docker-Container neu..."
        docker compose build
        docker compose up -d
        ;;
    2)
        cd $REPO_DIR/reader   
        echo "Reader wird gebaut..."
        echo "Baue Docker-Container neu..."
        docker compose build
        docker compose up -d
        ;;
    *)
        echo "Ungültige Auswahl. Bitte 1 oder 2 eingeben."
        exit 1
        ;;
esac