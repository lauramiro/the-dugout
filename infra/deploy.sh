#!/usr/bin/env bash
# Azure walking skeleton: resource group, Event Hubs, Web PubSub, Static Web Apps,
# Container Apps (decision service and live pipeline runner) and a budget alert.
#
# Dry run by default: prints every az command and runs nothing.
#   BUDGET_EMAIL=... infra/deploy.sh
# Create resources only after review and explicit approval:
#   BUDGET_EMAIL=... infra/deploy.sh --apply
#
# Required:  BUDGET_EMAIL  address that receives the budget alert; infra/foundry.sh run first (both
#            Container Apps narrate through its model deployment)
# Optional:  REGION (default northeurope; westeurope refused new customers on the free
#            subscription), SWA_REGION (default eastus2; westeurope refused, northeurope not offered), BUDGET_USD (default 20),
#            PREFIX (default dugout)
#
# Idempotent: each create is an upsert or is skipped when the resource exists.
# Secrets are read into shell variables and passed on, never echoed or written to disk,
# except the local .env (git-ignored) written for the replayer.
#
# Checked against `az ... -h`: containerapp up/env create/secret set/update, staticwebapp secrets list,
# eventhubs keys list. Still UNVERIFIED: webpubsub key show, budget create-with-rg input shapes, and the
# output property names primaryConnectionString / apiKey, and for the runner the service app's
# properties.configuration.registries[0] (server, username, passwordSecretRef) and
# properties.template.containers[0].image. `--check-help` prints the help for these.
#
# Two Container Apps from one image (built once, by `containerapp up` on the service): $PREFIX-service runs
# the Dockerfile's decision service; $PREFIX-runner runs the live pipeline (Event Hubs in, Web PubSub out)
# with a command of its own, no ingress and one replica (no checkpoint store, so a second replica would
# publish everything twice). It replaces the old $PREFIX-stub app, which this script no longer touches.
set -euo pipefail

APPLY=0
case "${1:-}" in
  --apply) APPLY=1 ;;
  --check-help) CHECK_HELP=1 ;;
  "") ;;
  *) echo "usage: $0 [--apply|--check-help]" >&2; exit 2 ;;
esac

if [[ "${CHECK_HELP:-0}" == 1 ]]; then
  for c in "containerapp up" "containerapp env create" "containerapp secret set" \
           "containerapp update" "containerapp create" "containerapp secret list" "containerapp show" "staticwebapp secrets list" \
           "eventhubs namespace authorization-rule keys list" "webpubsub key show" \
           "webpubsub hub create" "consumption budget create-with-rg"; do
    echo "=== az $c -h"; az $c -h
  done
  exit 0
fi

REGION="${REGION:-northeurope}"
SWA_REGION="${SWA_REGION:-eastus2}"
: "${BUDGET_EMAIL:?set BUDGET_EMAIL}"
BUDGET_USD="${BUDGET_USD:-20}"
PREFIX="${PREFIX:-dugout}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RG="$PREFIX-rg"
HUB="matchevents"
PUBSUB_HUB="decisions"

# Names of Event Hubs, Web PubSub and Static Web Apps are global; suffix from the subscription id.
if [[ $APPLY == 1 ]]; then
  SUFFIX="$(az account show --query id -o tsv | md5sum | cut -c1-6)"
else
  SUFFIX="xxxxxx"
fi
EH_NS="$PREFIX-eh-$SUFFIX"
WPS="$PREFIX-wps-$SUFFIX"
SWA="$PREFIX-web-$SUFFIX"
CAE="$PREFIX-env"
FOUNDRY="$PREFIX-foundry-$SUFFIX"  # created by infra/foundry.sh
APP="$PREFIX-service"
RUNNER="$PREFIX-runner"

run() { echo "+ $*"; [[ $APPLY == 1 ]] && "$@"; return 0; }
# For commands whose arguments carry secrets: print the label only.
run_quiet() {
  local label="$1"; shift
  # a dry run holds only placeholders, so it may show the command in full
  if [[ $APPLY == 1 ]]; then echo "+ ($label; arguments hidden)"; "$@"; else echo "+ $*"; fi
  return 0
}
# Capture a value; in a dry run return a placeholder.
capture() { if [[ $APPLY == 1 ]]; then "$@"; else echo "<dry-run>"; fi; }

# Abort when a captured value is empty (a wrong --query property comes back empty or "None").
need() { if [[ $APPLY == 1 && ( -z "$2" || "$2" == "None" ) ]]; then echo "empty value for $1; check the --query" >&2; exit 1; fi; }

echo "mode: $([[ $APPLY == 1 ]] && echo APPLY || echo dry run)  region: $REGION  swa region: $SWA_REGION"

echo "# 0. resource providers (new subscriptions have most unregistered) and CLI extensions"
for ns in Microsoft.EventHub Microsoft.SignalRService Microsoft.Web Microsoft.App           Microsoft.OperationalInsights Microsoft.ContainerRegistry; do
  run az provider register --namespace "$ns" --wait
done
run az extension add --name containerapp --upgrade --only-show-errors
run az extension add --name webpubsub --upgrade --only-show-errors

echo "# 1. resource group"
# An existing group keeps its location (changing it is an error); resources can sit elsewhere.
if [[ $APPLY == 1 && "$(az group exists --name "$RG")" == true ]]; then
  echo "resource group $RG exists, keeping it"
else
  run az group create --name "$RG" --location "$REGION" --output none
fi

echo "# 2. Event Hubs namespace and hub"
run az eventhubs namespace create --name "$EH_NS" --resource-group "$RG" --location "$REGION" --sku Basic --output none
run az eventhubs eventhub create --name "$HUB" --namespace-name "$EH_NS" --resource-group "$RG" --partition-count 2 --cleanup-policy Delete --retention-time 24 --output none

echo "# 3. Web PubSub"
run az webpubsub create --name "$WPS" --resource-group "$RG" --location "$REGION" --sku Free_F1 --output none
# The hub needs no setup: Web PubSub creates a hub on first use.

echo "# 4. Static Web Apps (no repo: content is uploaded in step 7)"
run az staticwebapp create --name "$SWA" --resource-group "$RG" --location "$SWA_REGION" --sku Free --output none
SWA_HOST="$(capture az staticwebapp show --name "$SWA" --resource-group "$RG" --query defaultHostname -o tsv)"

need SWA_HOST "$SWA_HOST"

echo "# 5. Container Apps environment and decision service"
run az containerapp env create --name "$CAE" --resource-group "$RG" --location "$REGION"
WPS_CONN="$(capture az webpubsub key show --name "$WPS" --resource-group "$RG" --query primaryConnectionString -o tsv)"
# 'up' builds the repo Dockerfile in Azure and creates or updates the app.
need WPS_CONN "$WPS_CONN"
# Foundry narration (infra/foundry.sh): endpoint, key and the first model deployment's name.
FOUNDRY_KEY="$(capture az cognitiveservices account keys list --name "$FOUNDRY" --resource-group "$RG" --query key1 -o tsv)"
FOUNDRY_MODEL="$(capture az cognitiveservices account deployment list --name "$FOUNDRY" --resource-group "$RG" --query "[0].name" -o tsv)"
need FOUNDRY_KEY "$FOUNDRY_KEY"; need FOUNDRY_MODEL "$FOUNDRY_MODEL"
FOUNDRY_ENV=("FOUNDRY_ENDPOINT=https://$FOUNDRY.openai.azure.com" "FOUNDRY_API_KEY=secretref:foundry-key"
             "FOUNDRY_MODEL=$FOUNDRY_MODEL" "FOUNDRY_REASONING_EFFORT=minimal")
run az containerapp up --name "$APP" --resource-group "$RG" --environment "$CAE" \
  --source "$ROOT" --ingress external --target-port 8000
run_quiet "store Web PubSub connection string and Foundry key as secrets" \
  az containerapp secret set --name "$APP" --resource-group "$RG" \
  --secrets "wps-conn=$WPS_CONN" "foundry-key=$FOUNDRY_KEY"
run az containerapp update --name "$APP" --resource-group "$RG" --set-env-vars \
  "WEBPUBSUB_CONNECTION_STRING=secretref:wps-conn" "WEBPUBSUB_HUB=$PUBSUB_HUB" \
  "STUB_CORS_ORIGINS=https://$SWA_HOST" "${FOUNDRY_ENV[@]}"
SERVICE_FQDN="$(capture az containerapp show --name "$APP" --resource-group "$RG" --query properties.configuration.ingress.fqdn -o tsv)"

need SERVICE_FQDN "$SERVICE_FQDN"

EH_CONN="$(capture az eventhubs namespace authorization-rule keys list --namespace-name "$EH_NS" \
  --resource-group "$RG" --name RootManageSharedAccessKey --query primaryConnectionString -o tsv)"
need EH_CONN "$EH_CONN"

echo "# 5b. Live pipeline runner: the service's image, its own command"
# Same image and registry as the service app; the registry login is read from the service app.
IMAGE="$(capture az containerapp show --name "$APP" --resource-group "$RG" \
  --query "properties.template.containers[0].image" -o tsv)"
REG_SERVER="$(capture az containerapp show --name "$APP" --resource-group "$RG" \
  --query "properties.configuration.registries[0].server" -o tsv)"
REG_USER="$(capture az containerapp show --name "$APP" --resource-group "$RG" \
  --query "properties.configuration.registries[0].username" -o tsv)"
REG_PW_REF="$(capture az containerapp show --name "$APP" --resource-group "$RG" \
  --query "properties.configuration.registries[0].passwordSecretRef" -o tsv)"
need IMAGE "$IMAGE"; need REG_SERVER "$REG_SERVER"; need REG_USER "$REG_USER"; need REG_PW_REF "$REG_PW_REF"
REG_PASS="$(capture az containerapp secret list --name "$APP" --resource-group "$RG" --show-values \
  --query "[?name=='$REG_PW_REF'].value | [0]" -o tsv)"
need REG_PASS "$REG_PASS"
# The command has no flags (az would read them as its own): PIPELINE_SOURCE selects Event Hubs and follow mode.
if [[ $APPLY == 1 ]] && az containerapp show --name "$RUNNER" --resource-group "$RG" >/dev/null 2>&1; then
  run az containerapp update --name "$RUNNER" --resource-group "$RG" --image "$IMAGE"
  run_quiet "refresh runner secrets" az containerapp secret set --name "$RUNNER" --resource-group "$RG" \
    --secrets "wps-conn=$WPS_CONN" "eh-conn=$EH_CONN" "acr-pw=$REG_PASS" "foundry-key=$FOUNDRY_KEY"
  run az containerapp update --name "$RUNNER" --resource-group "$RG" --set-env-vars "${FOUNDRY_ENV[@]}"
else
  run_quiet "create runner (secrets and registry password in arguments)" \
    az containerapp create --name "$RUNNER" --resource-group "$RG" --environment "$CAE" \
    --image "$IMAGE" --command python /app/dugout/stream/pipeline.py \
    --min-replicas 1 --max-replicas 1 \
    --registry-server "$REG_SERVER" --registry-username "$REG_USER" --registry-password secretref:acr-pw \
    --secrets "wps-conn=$WPS_CONN" "eh-conn=$EH_CONN" "acr-pw=$REG_PASS" "foundry-key=$FOUNDRY_KEY" \
    --env-vars "${FOUNDRY_ENV[@]}" "PIPELINE_SOURCE=eventhub" "EVENTHUB_CONNECTION_STRING=secretref:eh-conn" \
    "EVENTHUB_NAME=$HUB" "WEBPUBSUB_CONNECTION_STRING=secretref:wps-conn" "WEBPUBSUB_HUB=$PUBSUB_HUB"
fi

echo "# 6. Local .env for the replayer (git-ignored)"
if [[ $APPLY == 1 ]]; then
  umask 077
  # Replace only these two keys; other settings (FOUNDRY_*) stay.
  OTHERS="$(grep -v -E '^(EVENTHUB_CONNECTION_STRING|EVENTHUB_NAME)=' "$ROOT/.env" 2>/dev/null || true)"
  { [[ -n "$OTHERS" ]] && echo "$OTHERS"
    echo "EVENTHUB_CONNECTION_STRING=$EH_CONN"; echo "EVENTHUB_NAME=$HUB"; } > "$ROOT/.env"
  echo "updated EVENTHUB_* in $ROOT/.env"
else
  echo "+ (set EVENTHUB_CONNECTION_STRING and EVENTHUB_NAME in $ROOT/.env, keeping other lines)"
fi

echo "# 7. Build and upload the web page"
run bash -c "cd '$ROOT/web' && npm ci && npm run build"
run bash -c "printf '{ \"stubUrl\": \"https://%s\" }\n' '$SERVICE_FQDN' > '$ROOT/web/out/config.json'"
SWA_TOKEN="$(capture az staticwebapp secrets list --name "$SWA" --resource-group "$RG" --query properties.apiKey -o tsv)"
need SWA_TOKEN "$SWA_TOKEN"
if [[ $APPLY == 1 ]]; then
  SWA_CLI_DEPLOYMENT_TOKEN="$SWA_TOKEN" npx --yes @azure/static-web-apps-cli@2.0.10 deploy "$ROOT/web/out" --env production
else
  echo "+ (npx @azure/static-web-apps-cli@2.0.10 deploy web/out --env production; token via SWA_CLI_DEPLOYMENT_TOKEN)"
fi

echo "# 8. Budget alert on the resource group"
START="$(date -u +%Y-%m-01T00:00:00Z)"
END="$(date -u -d '+1 year' +%Y-%m-01T00:00:00Z)"
TMP="$(mktemp -d)"
cat > "$TMP/notifications.json" <<JSON
{
  "actual80": {"enabled": true, "operator": "GreaterThan", "threshold": 80,
               "contact-emails": ["$BUDGET_EMAIL"]},
  "actual100": {"enabled": true, "operator": "GreaterThan", "threshold": 100,
                "contact-emails": ["$BUDGET_EMAIL"]}
}
JSON
echo "{\"start-date\": \"$START\", \"end-date\": \"$END\"}" > "$TMP/period.json"
run az consumption budget create-with-rg --resource-group "$RG" --budget-name "$PREFIX-budget" \
  --amount "$BUDGET_USD" --category Cost --time-grain Monthly \
  --time-period "@$TMP/period.json" --notifications "@$TMP/notifications.json" --output none
rm -rf "$TMP"

echo
echo "page: https://$SWA_HOST"
echo "service: https://$SERVICE_FQDN/healthz"
echo "runner: $RUNNER (logs: az containerapp logs show --name $RUNNER --resource-group $RG --follow)"
