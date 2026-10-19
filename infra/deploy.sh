#!/usr/bin/env bash
# Azure walking skeleton: resource group, Event Hubs, Web PubSub, Static Web Apps,
# Container Apps (stub engine) and a budget alert.
#
# Dry run by default: prints every az command and runs nothing.
#   BUDGET_EMAIL=... infra/deploy.sh
# Create resources only after review and explicit approval:
#   BUDGET_EMAIL=... infra/deploy.sh --apply
#
# Required:  BUDGET_EMAIL  address that receives the budget alert
# Optional:  REGION (default northeurope; westeurope refused new customers on the free
#            subscription), SWA_REGION (default westeurope), BUDGET_USD (default 20),
#            PREFIX (default dugout)
#
# Idempotent: each create is an upsert or is skipped when the resource exists.
# Secrets are read into shell variables and passed on, never echoed or written to disk,
# except the local .env (git-ignored) written for the replayer.
#
# Checked against `az ... -h`: containerapp up/env create/secret set/update, staticwebapp secrets list,
# eventhubs keys list. Still UNVERIFIED: webpubsub key show, budget create-with-rg input shapes, and the
# output property names primaryConnectionString / apiKey. `--check-help` prints the help for these.
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
           "containerapp update" "staticwebapp secrets list" \
           "eventhubs namespace authorization-rule keys list" "webpubsub key show" \
           "webpubsub hub create" "consumption budget create-with-rg"; do
    echo "=== az $c -h"; az $c -h
  done
  exit 0
fi

REGION="${REGION:-northeurope}"
SWA_REGION="${SWA_REGION:-westeurope}"
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
APP="$PREFIX-stub"

run() { echo "+ $*"; [[ $APPLY == 1 ]] && "$@"; return 0; }
# For commands whose arguments carry secrets: print the label only.
run_quiet() { local label="$1"; shift; echo "+ ($label; arguments hidden)"; [[ $APPLY == 1 ]] && "$@"; return 0; }
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

echo "# 5. Container Apps environment and stub engine "
run az containerapp env create --name "$CAE" --resource-group "$RG" --location "$REGION"
WPS_CONN="$(capture az webpubsub key show --name "$WPS" --resource-group "$RG" --query primaryConnectionString -o tsv)"
# 'up' builds the repo Dockerfile in Azure and creates or updates the app.
need WPS_CONN "$WPS_CONN"
run az containerapp up --name "$APP" --resource-group "$RG" --environment "$CAE" \
  --source "$ROOT" --ingress external --target-port 8000
run_quiet "store Web PubSub connection string as secret" \
  az containerapp secret set --name "$APP" --resource-group "$RG" --secrets "wps-conn=$WPS_CONN"
run az containerapp update --name "$APP" --resource-group "$RG" --set-env-vars \
  "WEBPUBSUB_CONNECTION_STRING=secretref:wps-conn" "WEBPUBSUB_HUB=$PUBSUB_HUB" \
  "STUB_CORS_ORIGINS=https://$SWA_HOST"
STUB_FQDN="$(capture az containerapp show --name "$APP" --resource-group "$RG" --query properties.configuration.ingress.fqdn -o tsv)"

need STUB_FQDN "$STUB_FQDN"

echo "# 6. Local .env for the replayer (git-ignored)"
EH_CONN="$(capture az eventhubs namespace authorization-rule keys list --namespace-name "$EH_NS" \
  --resource-group "$RG" --name RootManageSharedAccessKey --query primaryConnectionString -o tsv)"
need EH_CONN "$EH_CONN"
if [[ $APPLY == 1 ]]; then
  umask 077
  { echo "EVENTHUB_CONNECTION_STRING=$EH_CONN"; echo "EVENTHUB_NAME=$HUB"; } > "$ROOT/.env"
  echo "wrote $ROOT/.env"
else
  echo "+ (write EVENTHUB_CONNECTION_STRING and EVENTHUB_NAME to $ROOT/.env)"
fi

echo "# 7. Build and upload the web page"
run bash -c "cd '$ROOT/web' && npm ci && npm run build"
run bash -c "printf '{ \"stubUrl\": \"https://%s\" }\n' '$STUB_FQDN' > '$ROOT/web/out/config.json'"
SWA_TOKEN="$(capture az staticwebapp secrets list --name "$SWA" --resource-group "$RG" --query properties.apiKey -o tsv)"
need SWA_TOKEN "$SWA_TOKEN"
if [[ $APPLY == 1 ]]; then
  SWA_CLI_DEPLOYMENT_TOKEN="$SWA_TOKEN" npx --yes @azure/static-web-apps-cli@2.0.10 deploy "$ROOT/web/out" --env production
else
  echo "+ (npx @azure/static-web-apps-cli@2.0.10 deploy web/out --env production; token via SWA_CLI_DEPLOYMENT_TOKEN)"
fi

echo "# 8. Budget alert on the resource group (UNVERIFIED: create-with-rg input shapes)"
START="$(date -u +%Y-%m-01T00:00:00Z)"
END="$(date -u -d '+1 year' +%Y-%m-01T00:00:00Z)"
TMP="$(mktemp -d)"
cat > "$TMP/notifications.json" <<JSON
{
  "actual80": {"enabled": true, "operator": "GreaterThan", "threshold": 80, "thresholdType": "Actual",
               "contactEmails": ["$BUDGET_EMAIL"]},
  "forecast100": {"enabled": true, "operator": "GreaterThan", "threshold": 100, "thresholdType": "Forecasted",
                  "contactEmails": ["$BUDGET_EMAIL"]}
}
JSON
echo "{\"startDate\": \"$START\", \"endDate\": \"$END\"}" > "$TMP/period.json"
run az consumption budget create-with-rg --resource-group "$RG" --budget-name "$PREFIX-budget" \
  --amount "$BUDGET_USD" --category Cost --time-grain Monthly \
  --time-period "@$TMP/period.json" --notifications "@$TMP/notifications.json" --output none
rm -rf "$TMP"

echo
echo "page: https://$SWA_HOST"
echo "stub: https://$STUB_FQDN/decision"
