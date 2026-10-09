import type { EvidenceRecord, ObjectType } from "@/api/types";
import { recordKey, type EvidenceRelation, type InsightRecord } from "../evidence";

// Deterministic two-column schematic: companies on the left as hubs, every
// other record on the right grouped by type. Edges run left to right, or as a
// short arc when both ends share a column. Pure so it can be unit tested.

export const NODE_W = 150;
export const NODE_H = 30;
export const ROW_H = 38;
export const GROUP_H = 22;
export const COL_GAP = 72;
export const PAD = 8;

export const TYPE_LABELS: Record<ObjectType, string> = {
  companies: "Companies", contacts: "Contacts", deals: "Deals", tickets: "Tickets", products: "Products",
  line_items: "Line items", notes: "Notes", calls: "Calls", emails: "Emails", meetings: "Meetings", tasks: "Tasks",
};

const ORDER: ObjectType[] = ["contacts", "deals", "tickets", "line_items", "products", "notes", "calls", "emails", "meetings", "tasks"];

export interface GraphNode {
  record: InsightRecord;
  key: string;
  x: number;
  y: number;
  column: "hub" | "member";
}

export interface GraphGroup {
  type: ObjectType;
  label: string;
  x: number;
  y: number;
  count: number;
}

export interface GraphEdge {
  from: string;
  to: string;
  path: string;
}

export interface GraphLayout {
  width: number;
  height: number;
  nodes: GraphNode[];
  groups: GraphGroup[];
  edges: GraphEdge[];
}

function single(a: EvidenceRecord): string {
  return recordKey(a);
}

export function layoutGraph(records: InsightRecord[], relations: EvidenceRelation[]): GraphLayout {
  const hubs = records.filter((record) => record.type === "companies");
  const members = records.filter((record) => record.type !== "companies");
  const hasHubs = hubs.length > 0;
  const hubX = PAD;
  const memberX = hasHubs ? PAD + NODE_W + COL_GAP : PAD;
  const width = memberX + NODE_W + PAD;

  const nodes: GraphNode[] = [];
  const groups: GraphGroup[] = [];
  const byKey = new Map<string, GraphNode>();

  let y = PAD;
  hubs.forEach((record) => {
    const node: GraphNode = { record, key: record.key, x: hubX, y, column: "hub" };
    nodes.push(node);
    byKey.set(node.key, node);
    y += ROW_H;
  });
  const hubHeight = y;

  let my = PAD;
  for (const type of ORDER) {
    const rows = members.filter((record) => record.type === type);
    if (!rows.length) continue;
    groups.push({ type, label: TYPE_LABELS[type], x: memberX, y: my, count: rows.length });
    my += GROUP_H;
    for (const record of rows) {
      const node: GraphNode = { record, key: record.key, x: memberX, y: my, column: "member" };
      nodes.push(node);
      byKey.set(node.key, node);
      my += ROW_H;
    }
    my += 6;
  }
  const height = Math.max(hubHeight, my) + PAD;

  // Hubs sit vertically centred against their members when there is one hub.
  if (hubs.length === 1 && members.length > 0) {
    const hub = nodes[0]!;
    hub.y = Math.max(PAD, Math.round((height - NODE_H) / 2));
  }

  const edges: GraphEdge[] = [];
  for (const relation of relations) {
    const a = byKey.get(single(relation.from));
    const b = byKey.get(single(relation.to));
    if (!a || !b) continue;
    const [left, right] = a.x <= b.x ? [a, b] : [b, a];
    if (left.column !== right.column) {
      const x1 = left.x + NODE_W, y1 = left.y + NODE_H / 2;
      const x2 = right.x, y2 = right.y + NODE_H / 2;
      const mid = Math.round((x1 + x2) / 2);
      edges.push({ from: a.key, to: b.key, path: `M${x1},${y1} C${mid},${y1} ${mid},${y2} ${x2},${y2}` });
    } else {
      // Same column: a small arc on the right-hand edge, deeper for longer spans.
      const x = left.x + NODE_W, y1 = left.y + NODE_H / 2, y2 = right.y + NODE_H / 2;
      const bulge = Math.min(28, 10 + Math.abs(y2 - y1) / 6);
      edges.push({ from: a.key, to: b.key, path: `M${x},${y1} C${x + bulge},${y1} ${x + bulge},${y2} ${x},${y2}` });
    }
  }
  return { width, height, nodes, groups, edges };
}
