"use client";

import { useMemo, useState } from "react";
import type { StrategyVersion } from "@/lib/strategies";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

// Minimal line-level diff. O(n*m) — fine for strategy code which is rarely
// over a few hundred lines. Produces a list of "common", "add", "remove"
// chunks suitable for a unified-diff render.

type DiffLine =
  | { kind: "common"; left: number; right: number; text: string }
  | { kind: "remove"; left: number; text: string }
  | { kind: "add"; right: number; text: string };

function diffLines(a: string, b: string): DiffLine[] {
  const A = a.split("\n");
  const B = b.split("\n");
  const m = A.length;
  const n = B.length;
  // LCS table
  const dp: number[][] = Array.from({ length: m + 1 }, () => Array(n + 1).fill(0));
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      if (A[i] === B[j]) dp[i][j] = dp[i + 1][j + 1] + 1;
      else dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const out: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < m && j < n) {
    if (A[i] === B[j]) {
      out.push({ kind: "common", left: i + 1, right: j + 1, text: A[i] });
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      out.push({ kind: "remove", left: i + 1, text: A[i] });
      i++;
    } else {
      out.push({ kind: "add", right: j + 1, text: B[j] });
      j++;
    }
  }
  while (i < m) {
    out.push({ kind: "remove", left: i + 1, text: A[i] });
    i++;
  }
  while (j < n) {
    out.push({ kind: "add", right: j + 1, text: B[j] });
    j++;
  }
  return out;
}

export function VersionDiffDialog({
  version,
  versions,
}: {
  version: StrategyVersion;
  versions: StrategyVersion[];
}) {
  const [open, setOpen] = useState(false);

  // Comparator defaults to the latest version (versions are returned newest-first).
  const others = versions.filter((v) => v.id !== version.id);
  const defaultOther = others[0]?.id ?? "";
  const [compareWithId, setCompareWithId] = useState(defaultOther);

  const compareWith = versions.find((v) => v.id === compareWithId);
  const diff = useMemo(() => {
    if (!compareWith) return [];
    // Left = older, Right = newer. We sort by version number descending.
    const older = version.version <= compareWith.version ? version : compareWith;
    const newer = older === version ? compareWith : version;
    return diffLines(older.code, newer.code);
  }, [version, compareWith]);

  const stats = useMemo(() => {
    let adds = 0;
    let removes = 0;
    for (const d of diff) {
      if (d.kind === "add") adds++;
      else if (d.kind === "remove") removes++;
    }
    return { adds, removes };
  }, [diff]);

  const older = compareWith && version.version <= compareWith.version ? version : compareWith;
  const newer = older === version ? compareWith : version;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="ghost" className="h-6 px-1.5 text-[10px]">
          Diff
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>
            Diff: v{older?.version} → v{newer?.version}
          </DialogTitle>
          <DialogDescription className="flex items-center gap-2">
            <span>Compare against:</span>
            <select
              value={compareWithId}
              onChange={(e) => setCompareWithId(e.target.value)}
              className="rounded border bg-background px-2 py-0.5 text-xs"
            >
              {others.map((v) => (
                <option key={v.id} value={v.id}>
                  v{v.version} {v.message ? `— ${v.message}` : ""}
                </option>
              ))}
            </select>
            <span className="ml-2 font-mono text-[10px]">
              <span className="text-emerald-400">+{stats.adds}</span>{" "}
              <span className="text-rose-500">-{stats.removes}</span>
            </span>
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-[70vh] overflow-auto rounded border bg-muted/20">
          {diff.length === 0 ? (
            <p className="p-4 text-sm text-muted-foreground">No comparator selected.</p>
          ) : (
            <table className="w-full font-mono text-xs">
              <tbody>
                {diff.map((d, idx) => (
                  <tr
                    key={idx}
                    className={cn(
                      d.kind === "add" && "bg-emerald-500/10",
                      d.kind === "remove" && "bg-rose-500/10",
                    )}
                  >
                    <td className="w-10 select-none border-r border-border/40 px-2 text-right text-muted-foreground">
                      {d.kind === "remove" || d.kind === "common" ? (d.left ?? "") : ""}
                    </td>
                    <td className="w-10 select-none border-r border-border/40 px-2 text-right text-muted-foreground">
                      {d.kind === "add" || d.kind === "common" ? (d.right ?? "") : ""}
                    </td>
                    <td className="w-4 select-none px-1 text-muted-foreground">
                      {d.kind === "add" ? "+" : d.kind === "remove" ? "−" : " "}
                    </td>
                    <td className="whitespace-pre-wrap break-all px-2 py-0.5">{d.text}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
