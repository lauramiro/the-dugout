// What the Under the hood panel lists: the Azure and Microsoft services behind the screen
// and the stages of the narration workflow. From the README's "Built on Azure" table and
// Agents section; each id has a one-line job in lib/i18n.ts under `hood_<id>`.

export const HOOD_SERVICES = [
  { id: "eventhubs", name: "Azure Event Hubs" },
  { id: "containerapps", name: "Azure Container Apps" },
  { id: "registry", name: "Azure Container Registry" },
  { id: "foundry", name: "Microsoft Foundry (gpt-5-mini)" },
  { id: "agentframework", name: "Microsoft Agent Framework" },
  { id: "webpubsub", name: "Azure Web PubSub" },
  { id: "staticwebapps", name: "Azure Static Web Apps" },
  { id: "mcp", name: "MCP server" },
] as const;

/** The narration workflow in order; `check` stages are plain code, not a model. */
export const HOOD_CHAIN = [
  { id: "narrator", check: false },
  { id: "check1", check: true },
  { id: "localizer", check: false },
  { id: "check2", check: true },
] as const;

export const MCP_URL = "https://dugout-service.wittypond-73564413.northeurope.azurecontainerapps.io/mcp";
export const REPO_URL = "https://github.com/lauramiro/the-dugout";

/** The README's connect lines (MCP server section), shown to copy. */
export const CLAUDE_COMMAND = `claude mcp add --transport http the-dugout ${MCP_URL}`;
export const VSCODE_CONFIG = `{ "servers": { "the-dugout": { "type": "http", "url": "${MCP_URL}" } } }`;
