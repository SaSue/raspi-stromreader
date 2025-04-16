# Verwende das offizielle NGINX Alpine-Image
FROM nginx:alpine

# Maintainer (optional)
LABEL maintainer="dein.name@example.com"

# Eigene nginx.conf ins Image kopieren (überschreibt Standard)
COPY nginx.conf /etc/nginx/nginx.conf

# HTML-Dateien in das Standard-Webverzeichnis von NGINX kopieren
COPY html/ /usr/share/nginx/html/

# Port (standardmäßig 80)
EXPOSE 80

# Container starten mit NGINX im Vordergrund (bereits im Base Image definiert)
# kein CMD nötig, außer du willst was anpassen