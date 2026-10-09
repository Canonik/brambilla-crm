import { describe, expect, it } from "vitest";
import type { InsightRecord } from "../evidence";
import { NODE_H, NODE_W, layoutGraph } from "./layout";

const rec = (type: InsightRecord["type"], id: string, written = false): InsightRecord => ({ type, id, key: `${type}:${id}`, firstStep: 1, steps: [1], written });

describe("record graph layout", () => {
  it("puts companies in the hub column, groups members by type and never overlaps nodes", () => {
    const layout = layoutGraph(
      [rec("companies", "18"), rec("contacts", "77"), rec("deals", "42", true), rec("deals", "43"), rec("notes", "9")],
      [
        { from: { type: "companies", id: "18" }, to: { type: "contacts", id: "77" } },
        { from: { type: "companies", id: "18" }, to: { type: "deals", id: "42" } },
        { from: { type: "deals", id: "42" }, to: { type: "contacts", id: "77" } },
      ],
    );
    expect(layout.nodes.filter((node) => node.column === "hub")).toHaveLength(1);
    expect(layout.groups.map((group) => group.label)).toEqual(["Contacts", "Deals", "Notes"]);
    expect(layout.edges).toHaveLength(3);
    const boxes = layout.nodes.map((node) => [node.x, node.y, node.x + NODE_W, node.y + NODE_H]);
    for (let a = 0; a < boxes.length; a++) for (let b = a + 1; b < boxes.length; b++) {
      const [ax1, ay1, ax2, ay2] = boxes[a]!, [bx1, by1, bx2, by2] = boxes[b]!;
      expect(ax1 < bx2 && bx1 < ax2 && ay1 < by2 && by1 < ay2).toBe(false);
    }
    expect(layout.width).toBeLessThanOrEqual(420);
    expect(layout.height).toBeGreaterThan(0);
  });

  it("is deterministic and handles traces without companies", () => {
    const records = [rec("contacts", "1"), rec("tickets", "2")];
    const a = layoutGraph(records, []);
    const b = layoutGraph(records, []);
    expect(a).toEqual(b);
    expect(a.nodes.every((node) => node.column === "member")).toBe(true);
    expect(a.edges).toEqual([]);
  });
});
