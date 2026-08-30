#!/usr/bin/env bash
# Build and deploy the scheduled Playwright runner as a Cloud Run Job.
#
# The NovaCart repo is read-only, so its test suite is copied into a scratch
# build context and combined with the Dockerfile here. The copy is regenerated
# every run, so it cannot drift from the source.
set -euo pipefail

SRC="${SUITE_SRC:-$HOME/Desktop/TriageZero/playwright-tests}"
REGION="${REGION:-us-central1}"
PROJECT="${PROJECT:-triagezero}"
NOVA_WEB="${NOVACART_BASE_URL:?set NOVACART_BASE_URL to the novacart-web URL}"
TZ_API="${TRIAGEZERO_API_URL:?set TRIAGEZERO_API_URL to the triagezero-api URL}"
SCENARIO="${NOVACART_DEFECT_SCENARIO:-}"
RUNNER_SA="triagezero-runner@${PROJECT}.iam.gserviceaccount.com"

HERE="$(cd "$(dirname "$0")" && pwd)"
CTX="$HERE/.runner-build"
IMAGE="$REGION-docker.pkg.dev/$PROJECT/triagezero/test-runner:$(date +%s)"

echo "==> staging suite from $SRC"
rm -rf "$CTX"; mkdir -p "$CTX/suite"
cp "$HERE/runner/Dockerfile" "$HERE/runner/run.sh" "$CTX/"
rsync -a --exclude node_modules --exclude test-results --exclude .git \
      --exclude playwright-report "$SRC/" "$CTX/suite/"

# Read the version the suite actually resolves to, so the base image always
# carries the matching browsers.
PW_VERSION="$(python3 -c "
import json,sys
d=json.load(open('$CTX/suite/package-lock.json'))
print(d['packages']['node_modules/@playwright/test']['version'])
" 2>/dev/null || echo "")"
if [ -z "$PW_VERSION" ]; then
  echo "ERROR: could not read the Playwright version from the suite lockfile."
  echo "       Without it the image would ship mismatched browsers."
  exit 1
fi
echo "==> playwright version from lockfile: $PW_VERSION"

cat > "$CTX/cloudbuild.yaml" <<YAML
steps:
  - name: gcr.io/cloud-builders/docker
    args:
      - build
      - -t
      - '$IMAGE'
      - --build-arg
      - 'PLAYWRIGHT_VERSION=$PW_VERSION'
      - .
images:
  - '$IMAGE'
YAML

echo "==> building $IMAGE"
gcloud builds submit "$CTX" --project="$PROJECT" --config="$CTX/cloudbuild.yaml"

echo "==> deploying job"
gcloud run jobs deploy triagezero-scheduled-tests \
  --project="$PROJECT" --region="$REGION" \
  --image="$IMAGE" \
  --service-account="$RUNNER_SA" \
  --set-secrets=TRIAGEZERO_API_TOKEN=triagezero-ingestion-token:latest \
  --set-env-vars="NOVACART_BASE_URL=$NOVA_WEB,TRIAGEZERO_API_URL=$TZ_API,RUN_CONTROLLED_DEFECTS=true,NOVACART_DEFECT_SCENARIO=$SCENARIO,CI=true" \
  --max-retries=0 \
  --task-timeout=10m \
  --memory=2Gi --cpu=2

echo "==> done. Run it now with:"
echo "    gcloud run jobs execute triagezero-scheduled-tests --region=$REGION --wait"
