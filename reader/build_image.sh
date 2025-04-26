#!/bin/bash

# Basis-Registry
REGISTRY="registry.intranet.suechting.com"

# Prüfen, ob ein Argument übergeben wurde
if [ -n "$1" ]; then
    NAME_INPUT="$1"
    echo "📦 Image-Name übergeben: $NAME_INPUT"
else
    read -p "Gib den Image-Namen ein (z.B. raspi-status): " NAME_INPUT
fi

# Vollständiger Image-Name
IMAGE_NAME="${REGISTRY}/${NAME_INPUT}"

# Versuche, den Git-Tag zu holen
if GIT_TAG=$(sudo git describe --tags --abbrev=0 2>/dev/null); then
    VERSION="$GIT_TAG"
    echo "✅ Git-Tag gefunden: $VERSION"
else
    VERSION=$(date +%Y%m%d%H%M%S)
    echo "⚠️ Kein Git-Tag gefunden. Verwende Datum als Version: $VERSION"
fi

# Docker-Image bauen
sudo docker build -t ${IMAGE_NAME}:${VERSION} .

# "latest"-Tag setzen
sudo docker tag ${IMAGE_NAME}:${VERSION} ${IMAGE_NAME}:latest

echo "✅ Image gebaut:"
echo " - ${IMAGE_NAME}:${VERSION}"
echo " - ${IMAGE_NAME}:latest"

# Abfrage ob pushen
read -p "Willst du das Image pushen? (j/n): " PUSH

if [[ "$PUSH" == "j" || "$PUSH" == "J" ]]; then
    echo "🚀 Pushe Images zur Registry..."
    sudo docker push ${IMAGE_NAME}:${VERSION}
    sudo docker push ${IMAGE_NAME}:latest
    echo "✅ Push abgeschlossen."
else
    echo "⏭️ Push übersprungen."
fi
