#!/usr/bin/env bash
# Azure walking skeleton: resource group, Event Hubs, Web PubSub, Static Web Apps,
# Container Apps (decision service, live pipeline runner and a scheduled replay job) and a budget alert.
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
#            PREFIX (default dugout), LIVE_EVERY_MIN (default 30: the demo match kicks off every
#            30 minutes from midnight UTC; 0 skips the replay job), LIVE_SPEED (default 5)
#            WPS_SKU (default Free_F1: 20 connections, 20,000 messages a day; Standard_S1 for judging days)
#
# Idempotent: each create is an upsert or is skipped when the resource exists.
# Secrets are read into shell variables and passed on, never echoed or written to disk,
# except the local .env (git-ignored) written for the replayer.
#
# Checked against `az ... -h`: containerapp up/env create/secret set/update, staticwebapp secrets list,
# eventhubs keys list, containerapp create --registry-identity. Verified by the 2026-10-21 apply:
# webpubsub key show primaryConnectionString, the service app's image and registries[0].server (its
# username is empty: it pulls with its system identity). The same apply's web upload confirmed
# staticwebapp secrets list properties.apiKey, and a budget create-with-rg run confirmed its
# @file input shapes. `--check-help` prints the help for these.
#
# Two Container Apps from one image (built once, by `containerapp up` on the service): $PREFIX-service runs
# the Dockerfile's decision service; $PREFIX-runner runs the live pipeline (Event Hubs in, Web PubSub out)
# with a command of its own, no ingress and one replica (no checkpoint store, so a second replica would
# publish everything twice). It replaces the old $PREFIX-stub app, which this script no longer touches.
# $PREFIX-replay is a scheduled Container Apps job on the same image: two minutes before each kick-off
# slot it starts dugout/stream/replay.py, which waits for the slot and replays the demo match into
# Event Hubs for the runner. The page reads the same schedule from schedule.json (step 7).
# Checked against Microsoft Learn (az containerapp job, 2026-09 CLI reference; jobs concepts page:
# cron in UTC, five fields), not yet by an apply.
set -euo pipefail
# Git Bash on Windows rewrites /app/... arguments into C:/Program Files/Git/app/...; keep them as written.
export MSYS_NO_PATHCONV=1

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
           "webpubsub hub create" "consumption budget create-with-rg"            "containerapp job create" "containerapp job update" "containerapp job secret set"; do
    echo "=== az $c -h"; az $c -h
  done
  exit 0
fi

REGION="${REGION:-northeurope}"
SWA_REGION="${SWA_REGION:-eastus2}"
: "${BUDGET_EMAIL:?set BUDGET_EMAIL}"
BUDGET_USD="${BUDGET_USD:-20}"
PREFIX="${PREFIX:-dugout}"
LIVE_EVERY_MIN="${LIVE_EVERY_MIN:-30}"
LIVE_SPEED="${LIVE_SPEED:-5}"
WPS_SKU="${WPS_SKU:-Free_F1}"
# The job starts two minutes before each slot, so slots must be at least 5 minutes apart.
if (( LIVE_EVERY_MIN != 0 && (LIVE_EVERY_MIN < 5 || 60 % LIVE_EVERY_MIN != 0) )); then
  echo "LIVE_EVERY_MIN must be 0 or a divisor of 60 from 5 up" >&2; exit 2
fi
# A match must end before the next kick-off: about 100 minutes at 1x, 20 at 5x, 5 at 20x.
case "$LIVE_SPEED" in 1) MIN_EVERY=61 ;; 5) MIN_EVERY=30 ;; 20) MIN_EVERY=10 ;;
  *) echo "LIVE_SPEED must be 1, 5 or 20" >&2; exit 2 ;; esac
if (( LIVE_EVERY_MIN != 0 && LIVE_EVERY_MIN < MIN_EVERY )); then
  echo "at ${LIVE_SPEED}x a match overruns a ${LIVE_EVERY_MIN}-minute slot (slots are at most 60)" >&2; exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# With path conversion off, Windows programs (az, npx) need C:/Users/... rather than /c/Users/...;
# that form also works in Git Bash itself.
if command -v cygpath >/dev/null; then ROOT="$(cygpath -m "$ROOT")"; fi
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
REPLAY_JOB="$PREFIX-replay"
DEMO_EVENTS="data/demo-rfc-cas-0073.jsonl"  # copied into the image by the Dockerfile

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
# An existing service keeps its data and keys; a tier change goes through update (create would reset
# it to the tier given). Free_F1 to Standard_S1 moves the service, with a gap of up to an hour.
if [[ $APPLY == 1 ]] && az webpubsub show --name "$WPS" --resource-group "$RG" >/dev/null 2>&1; then
  if [[ "$(az webpubsub show --name "$WPS" --resource-group "$RG" --query sku.name -o tsv)" != "$WPS_SKU" ]]; then
    run az webpubsub update --name "$WPS" --resource-group "$RG" --sku "$WPS_SKU" --unit-count 1 --output none
  else
    echo "web pubsub $WPS is already $WPS_SKU, keeping it"
  fi
else
  run az webpubsub create --name "$WPS" --resource-group "$RG" --location "$REGION" --sku "$WPS_SKU" --unit-count 1 --output none
fi
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
# Same image and registry as the service app. `containerapp up` (CLI 2.91) pulls with the app's
# system identity, not a username and password, so the runner gets its own system identity too.
IMAGE="$(capture az containerapp show --name "$APP" --resource-group "$RG" \
  --query "properties.template.containers[0].image" -o tsv)"
REG_SERVER="$(capture az containerapp show --name "$APP" --resource-group "$RG" \
  --query "properties.configuration.registries[0].server" -o tsv)"
need IMAGE "$IMAGE"; need REG_SERVER "$REG_SERVER"
# The command has no flags (az would read them as its own): PIPELINE_SOURCE selects Event Hubs and follow mode.
if [[ $APPLY == 1 ]] && az containerapp show --name "$RUNNER" --resource-group "$RG" >/dev/null 2>&1; then
  run az containerapp update --name "$RUNNER" --resource-group "$RG" --image "$IMAGE"
  run_quiet "refresh runner secrets" az containerapp secret set --name "$RUNNER" --resource-group "$RG" \
    --secrets "wps-conn=$WPS_CONN" "eh-conn=$EH_CONN" "foundry-key=$FOUNDRY_KEY"
  run az containerapp update --name "$RUNNER" --resource-group "$RG" --set-env-vars "${FOUNDRY_ENV[@]}"
else
  run_quiet "create runner (secrets in arguments)" \
    az containerapp create --name "$RUNNER" --resource-group "$RG" --environment "$CAE" \
    --image "$IMAGE" --command python /app/dugout/stream/pipeline.py \
    --min-replicas 1 --max-replicas 1 \
    --registry-server "$REG_SERVER" --registry-identity system \
    --secrets "wps-conn=$WPS_CONN" "eh-conn=$EH_CONN" "foundry-key=$FOUNDRY_KEY" \
    --env-vars "${FOUNDRY_ENV[@]}" "PIPELINE_SOURCE=eventhub" "EVENTHUB_CONNECTION_STRING=secretref:eh-conn" \
    "EVENTHUB_NAME=$HUB" "WEBPUBSUB_CONNECTION_STRING=secretref:wps-conn" "WEBPUBSUB_HUB=$PUBSUB_HUB"
fi

echo "# 5c. Scheduled replay: the demo match every $LIVE_EVERY_MIN minutes at ${LIVE_SPEED}x"
if [[ $LIVE_EVERY_MIN == 0 ]]; then
  echo "skipped (LIVE_EVERY_MIN=0); an existing $REPLAY_JOB job is left as it is"
else
  # Two minutes before each slot (UTC): 28,58 for every 30 minutes. replay.py then waits for the slot,
  # so the container's start-up time does not move the kick-off.
  CRON="$(seq $((LIVE_EVERY_MIN - 2)) "$LIVE_EVERY_MIN" 59 | paste -sd, -) * * * *"
  # No flags in the command (az would read them as its own): REPLAY_* stand in for them.
  REPLAY_ENV=("REPLAY_EVENTS=/app/$DEMO_EVENTS" "REPLAY_SPEED=$LIVE_SPEED" "REPLAY_EVERY_MIN=$LIVE_EVERY_MIN"
              "EVENTHUB_CONNECTION_STRING=secretref:eh-conn" "EVENTHUB_NAME=$HUB")
  # Two minutes early plus about 20 minutes of match at 5x fit in the 30-minute timeout; no retry
  # (a retry would kick off mid-slot).
  if [[ $APPLY == 1 ]] && az containerapp job show --name "$REPLAY_JOB" --resource-group "$RG" >/dev/null 2>&1; then
    run_quiet "refresh replay job secret" az containerapp job secret set --name "$REPLAY_JOB" --resource-group "$RG"       --secrets "eh-conn=$EH_CONN"
    run az containerapp job update --name "$REPLAY_JOB" --resource-group "$RG" --image "$IMAGE"       --cron-expression "$CRON" --set-env-vars "${REPLAY_ENV[@]}"
  else
    run_quiet "create replay job (secret in arguments)"       az containerapp job create --name "$REPLAY_JOB" --resource-group "$RG" --environment "$CAE"       --trigger-type Schedule --cron-expression "$CRON"       --replica-timeout 1800 --replica-retry-limit 0 --parallelism 1 --replica-completion-count 1       --image "$IMAGE" --command python /app/dugout/stream/replay.py --cpu 0.25 --memory 0.5Gi       --registry-server "$REG_SERVER" --registry-identity system       --secrets "eh-conn=$EH_CONN" --env-vars "${REPLAY_ENV[@]}"
  fi
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
# The kick-off times the live page counts down to; without the file it only waits for the feed.
if [[ $LIVE_EVERY_MIN != 0 ]]; then
  run bash -c "cd '$ROOT' && uv run python -m dugout.stream.replay '$DEMO_EVENTS' --speed '$LIVE_SPEED'     --every '$LIVE_EVERY_MIN' --write-schedule web/out/schedule.json"
fi
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
# az is a Windows program: give it the C:/ form of the temp folder, as for ROOT.
if command -v cygpath >/dev/null; then TMP="$(cygpath -m "$TMP")"; fi
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
echo "mcp: https://$SERVICE_FQDN/mcp"
echo "runner: $RUNNER (logs: az containerapp logs show --name $RUNNER --resource-group $RG --follow)"
if [[ $LIVE_EVERY_MIN != 0 ]]; then
  echo "replay job: $REPLAY_JOB, cron '$CRON' UTC (runs: az containerapp job execution list --name $REPLAY_JOB --resource-group $RG)"
fi
