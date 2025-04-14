docker stop strom-reader
docker remove strom-reader
docker stop strom-dashboard-frontend
docker remove strom-dashboard-frontend
docker stop strom-dashboard-backend
docker remove strom-dashboard-backend
cd ~/raspi-stromreader
docker compose down
docker network rm strom-network
cd ~
rm -rf raspi-stromreader
git clone https://SaSue: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@github.com/SaSue/raspi-stromreader.git
cd ~/raspi-stromreader
cp -v html/*.* /var/www/html
sed -i 's/DEBUG=1/DEBUG=0/' docker-compose.yml
docker compose build
docker compose up -d