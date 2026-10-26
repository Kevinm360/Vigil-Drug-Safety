#!/usr/bin/env bash
set -euo pipefail
# Run on EC2 from the repository root. Private vigil container/volume are untouched.
host=${1:?Usage: bash scripts/deploy-public-demo.sh your-name.duckdns.org}
[[ "$host" =~ ^[a-z0-9][a-z0-9-]*\.duckdns\.org$ ]] || { echo "Expected a DuckDNS hostname"; exit 1; }
config="$HOME/.config/vigil-public"
mkdir -p "$config"
chmod 700 "$config"
# Copy only the FDA key; never copy private workspace credentials.
python3 - "$host" "$config" <<'PYCODE'
import sys
from pathlib import Path
host, folder = sys.argv[1:]
source = Path.home() / '.config/vigil/vigil.env'
keys = [line for line in source.read_text().splitlines() if line.startswith('OPENFDA_API_KEY=')]
if not keys or not keys[-1].split('=', 1)[1]:
    raise SystemExit('Save your working FDA key before deploying.')
p = Path(folder) / 'demo.env'
p.write_text(keys[-1] + '\nVIGIL_PUBLIC_DEMO=1\nVIGIL_PUBLIC_ORIGIN=https://' + host + '\n')
p.chmod(0o600)
(Path(folder) / 'Caddyfile').write_text(host + ' {\n    reverse_proxy vigil-public:10000\n}\n')
PYCODE
sudo docker build -t vigil:public-demo .
sudo docker network inspect vigil-public-net >/dev/null 2>&1 || sudo docker network create vigil-public-net
sudo docker volume create vigil-public-data
sudo docker volume create vigil-caddy-data
sudo docker volume create vigil-caddy-config
if sudo docker container inspect vigil-public >/dev/null 2>&1; then sudo docker rm -f vigil-public; fi
sudo docker run -d --name vigil-public --restart unless-stopped \
  --network vigil-public-net --env-file "$config/demo.env" \
  --memory=700m --cpus=0.7 --pids-limit=128 \
  -v vigil-public-data:/var/data \
  --log-opt max-size=10m --log-opt max-file=3 vigil:public-demo
# No public application port. Only Caddy publishes 80/443.
sudo docker run --rm --network vigil-public-net \
  -v "$config/Caddyfile:/etc/caddy/Caddyfile:ro,Z" caddy:2 caddy validate --config /etc/caddy/Caddyfile
if sudo docker container inspect vigil-caddy >/dev/null 2>&1; then sudo docker rm -f vigil-caddy; fi
sudo docker run -d --name vigil-caddy --restart unless-stopped \
  --network vigil-public-net -p 80:80 -p 443:443 \
  -v "$config/Caddyfile:/etc/caddy/Caddyfile:ro,Z" \
  -v vigil-caddy-data:/data -v vigil-caddy-config:/config \
  --log-opt max-size=10m --log-opt max-file=3 caddy:2
echo "Started. Check: sudo docker logs --tail 30 vigil-caddy"
echo "Then open https://$host (DNS must point here and inbound TCP 80/443 must be allowed)."
