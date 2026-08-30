#!/usr/bin/env bash
# Build and deploy the NovaCart shopfront without modifying its repository.
#
# The NovaCart repo is read-only, so its source is copied into a scratch build
# context here, combined with the Dockerfile in deploy/novacart-web, and
# submitted to Cloud Build. The copy is regenerated every run, so it cannot
# drift from the source.
#
# A generated cloudbuild config is used rather than `--tag`, because Vite reads
# VITE_API_BASE_URL at BUILD time and `gcloud builds submit --tag` cannot pass
# build args. Without it the bundle falls back to http://localhost:8000 and the
# deployed shop silently shows no products.
set -euo pipefail

SRC="${NOVACART_SRC:-$HOME/Desktop/TriageZero/frontend}"
REGION="${REGION:-us-central1}"
PROJECT="${PROJECT:-triagezero}"
API_URL="${NOVACART_API_URL:?set NOVACART_API_URL to the novacart-api service URL}"
SCENARIO="${NOVACART_DEFECT_SCENARIO:-}"

HERE="$(cd "$(dirname "$0")" && pwd)"
CTX="$HERE/.novacart-build"
IMAGE="$REGION-docker.pkg.dev/$PROJECT/triagezero/novacart-web:$(date +%s)"

echo "==> staging source from $SRC"
rm -rf "$CTX"
mkdir -p "$CTX/app"
cp "$HERE/novacart-web/Dockerfile" "$HERE/novacart-web/nginx.conf.template" "$CTX/"
# node_modules and dist are rebuilt inside the image; copying them would drag
# the host platform's native binaries into a Linux container.
rsync -a --exclude node_modules --exclude dist --exclude .git "$SRC/" "$CTX/app/"

cat > "$CTX/cloudbuild.yaml" <<YAML
steps:
  - name: gcr.io/cloud-builders/docker
    args:
      - build
      - -t
      - '$IMAGE'
      - --build-arg
      - 'VITE_API_BASE_URL=$API_URL'
      - --build-arg
      - 'VITE_NOVACART_DEFECT_SCENARIO=$SCENARIO'
      - .
images:
  - '$IMAGE'
YAML

echo "==> building $IMAGE"
echo "    API base baked in: $API_URL"
echo "    defect scenario:   ${SCENARIO:-<none>}"
gcloud builds submit "$CTX" --project="$PROJECT" --config="$CTX/cloudbuild.yaml"

echo "==> deploying"
gcloud run deploy novacart-web \
  --project="$PROJECT" --region="$REGION" \
  --image="$IMAGE" \
  --allow-unauthenticated \
  --port=8080 \
  --min-instances=0 --max-instances=2 --memory=256Mi

gcloud run services describe novacart-web --project="$PROJECT" --region="$REGION" \
  --format='value(status.url)'
