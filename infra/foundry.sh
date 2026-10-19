#!/usr/bin/env bash
# Microsoft Foundry resource and one model deployment for the narration agents.
#
# Dry run by default: prints every az command and runs nothing.
#   infra/foundry.sh
# Create resources only after review and explicit approval (the deployment is billed per token):
#   infra/foundry.sh --apply
#
# Optional:  REGION (default uksouth), PREFIX (default dugout; the resource group is $PREFIX-rg,
#            reused when it exists), MODEL_NAME (default gpt-5.4-nano), MODEL_VERSION (default
#            2026-03-17), SKU (default GlobalStandard), CAPACITY (default 10, thousands of
#            tokens per minute for a Global Standard deployment)
#
# Checked against the Azure CLI reference for `az cognitiveservices account create` and
# `az cognitiveservices account deployment create` (flags below match it), and against the
# region table and retirement schedule in the Foundry docs. Not checked against a live
# subscription: a free subscription may refuse a region (deploy.sh hit that for westeurope), in
# which case rerun with another REGION that lists the model for Global Standard.
# `--check-help` prints the help for the commands used.
#
# Idempotent: the group and the account are skipped when they exist, the deployment is an upsert.
# Nothing is written to disk and no key is printed. The last lines say which variables to put in
# .env (names only, see env.example) and the command that reads the key.
set -euo pipefail

APPLY=0
case "${1:-}" in
  --apply) APPLY=1 ;;
  --check-help) CHECK_HELP=1 ;;
  "") ;;
  *) echo "usage: $0 [--apply|--check-help]" >&2; exit 2 ;;
esac

if [[ "${CHECK_HELP:-0}" == 1 ]]; then
  for c in "cognitiveservices account create" "cognitiveservices account deployment create" \
           "cognitiveservices account keys list"; do
    echo "=== az $c -h"; az $c -h
  done
  exit 0
fi

REGION="${REGION:-uksouth}"
PREFIX="${PREFIX:-dugout}"
MODEL_NAME="${MODEL_NAME:-gpt-5.4-nano}"
MODEL_VERSION="${MODEL_VERSION:-2026-03-17}"
SKU="${SKU:-GlobalStandard}"
CAPACITY="${CAPACITY:-10}"
RG="$PREFIX-rg"
DEPLOYMENT="$MODEL_NAME"

# The account name is also the global custom subdomain; suffix from the subscription id.
if [[ $APPLY == 1 ]]; then
  SUFFIX="$(az account show --query id -o tsv | md5sum | cut -c1-6)"
else
  SUFFIX="xxxxxx"
fi
ACCOUNT="$PREFIX-foundry-$SUFFIX"

run() { echo "+ $*"; [[ $APPLY == 1 ]] && "$@"; return 0; }

echo "mode: $([[ $APPLY == 1 ]] && echo APPLY || echo dry run)  region: $REGION  model: $MODEL_NAME $MODEL_VERSION ($SKU, capacity $CAPACITY)"

echo "# 0. resource provider"
run az provider register --namespace Microsoft.CognitiveServices --wait

echo "# 1. resource group"
if [[ $APPLY == 1 && "$(az group exists --name "$RG")" == true ]]; then
  echo "resource group $RG exists, keeping it"
else
  run az group create --name "$RG" --location "$REGION" --output none
fi

echo "# 2. Foundry resource (AIServices) with a custom subdomain for the endpoint"
if [[ $APPLY == 1 ]] && az cognitiveservices account show --name "$ACCOUNT" --resource-group "$RG" --output none 2>/dev/null; then
  echo "account $ACCOUNT exists, keeping it"
else
  run az cognitiveservices account create --name "$ACCOUNT" --resource-group "$RG" --location "$REGION" \
    --kind AIServices --sku S0 --custom-domain "$ACCOUNT" --yes --output none
fi

echo "# 3. model deployment"
run az cognitiveservices account deployment create --name "$ACCOUNT" --resource-group "$RG" \
  --deployment-name "$DEPLOYMENT" --model-name "$MODEL_NAME" --model-version "$MODEL_VERSION" \
  --model-format OpenAI --sku-name "$SKU" --sku-capacity "$CAPACITY" --output none

echo "# 4. next steps (nothing was written to disk)"
echo "Add to .env (names in env.example):"
echo "  FOUNDRY_ENDPOINT=https://$ACCOUNT.openai.azure.com"
echo "  FOUNDRY_MODEL=$DEPLOYMENT"
echo "  FOUNDRY_API_KEY=<output of the command below>"
echo "Read the key without printing it to a log:"
echo "  az cognitiveservices account keys list --name $ACCOUNT --resource-group $RG --query key1 -o tsv"
