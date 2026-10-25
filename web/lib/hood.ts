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

/** The architecture drawn in the panel itself (docs/architecture.svg is too wide to read inline): four lanes,
 *  each a row of nodes with a label on every link. A node with `brand` shows that product name as is; the others
 *  are named in lib/i18n.ts under `hoodNode_<id>`. Every node has a line under `hoodSub_<id>`, every link
 *  `hoodEdge_<id>`, every lane `hoodLane_<id>`. */
type FlowNode = { id: string; brand?: string };
export const HOOD_FLOW: readonly { id: string; nodes: readonly FlowNode[]; edges: readonly string[] }[] = [
  {
    id: "live",
    nodes: [{ id: "replayer" }, { id: "eventhubs", brand: "Azure Event Hubs" }, { id: "runner" },
      { id: "webpubsub", brand: "Azure Web PubSub" }, { id: "browser" }],
    edges: ["events", "consume", "publish", "socket"],
  },
  {
    id: "narration",
    nodes: [{ id: "runner" }, { id: "foundry", brand: "Microsoft Foundry" }],
    edges: ["workflow"],
  },
  {
    id: "request",
    nodes: [{ id: "staticwebapps", brand: "Azure Static Web Apps" }, { id: "browser" }, { id: "service" }],
    edges: ["page", "negotiate"],
  },
  {
    id: "agents",
    nodes: [{ id: "mcpclients" }, { id: "service" }, { id: "foundry", brand: "Microsoft Foundry" }],
    edges: ["mcp", "explain"],
  },
];

/** Every i18n key the drawn flow uses. */
export function flowKeys(): string[] {
  const keys = new Set<string>();
  for (const lane of HOOD_FLOW) {
    keys.add(`hoodLane_${lane.id}`);
    for (const node of lane.nodes) {
      if (!node.brand) keys.add(`hoodNode_${node.id}`);
      keys.add(`hoodSub_${node.id}`);
    }
    for (const edge of lane.edges) keys.add(`hoodEdge_${edge}`);
  }
  return [...keys];
}
