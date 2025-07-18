#!/bin/bash

# Gewünschter Git-Branch (default: main)
BRANCH="${1:-main}"
REPO_DIR=~/raspi-stromreader

# Auswahlmenü anzeigen
echo "Bitte wählen Sie eine Option:"
echo "1 = Dashboard bauen"
echo "2 = Reader bauen"
echo "3 = Dump des Leseroutputs"
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
    git clone --branch "$BRANCH" "https://github.com/SaSue/raspi-stromreader.git" "$REPO_DIR"
    cd "$REPO_DIR" || exit 1
fi

# sh ausführbar machen
chmod +x $REPO_DIR/strom.sh

# Auswahl ausführen
case $AUSWAHL in
    1)
        echo "Dashboard wird gebaut..."

        # Container neu bauen und starten
        cd $REPO_DIR/dashboard
        echo "Dashboard wird gebaut..."
        echo "Baue Docker-Container neu..."
        sudo docker compose build
        sudo docker compose up -d
        ;;
    2)
        cd $REPO_DIR/reader   
        echo "Reader wird gebaut..."
        echo "Baue Docker-Container neu..."
        sudo docker compose build
        sudo docker compose up -d
        ;;
    3)
        cd $REPO_DIR/reader-dump
        echo "Dump des Leseroutputs wird gestartet..."
        echo "Baue Docker-Container neu..."
        sudo docker compose build
        echo "Starte Docker-Container im Vordergrund..."
        sudo docker compose up
        ;;
    *)
        echo "Ungültige Auswahl. Bitte 1, 2 oder 3 eingeben."
        exit 1
        ;;
esac
