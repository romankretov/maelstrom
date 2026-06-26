"use client";

import { useMemo } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export type ParamSpec = {
  name: string;
  /** Default value as a literal Python string ("1000", "0.05", "'1h'"). */
  default: string;
  /** Best-guess kind from the literal — drives the input type. */
  kind: "number" | "string" | "bool";
};

/**
 * Scan strategy code for `self.params.get("name", default)` calls and pull
 * out the param name + default literal. Regex-based — the sandbox AST is
 * server-side and we don't want a wasm bundle just to parse Python here.
 *
 * We accept both single and double quoted names. Defaults are taken
 * verbatim, then type-classified by shape: numeric, boolean, or string.
 */
export function extractParams(code: string): ParamSpec[] {
  // self.params.get('name', default)  — default is a single token or a
  // simple literal (number, "string", True/False). For complex defaults
  // (function calls, expressions) we just drop the default and treat as
  // string. The user can still override via the form input.
  const re = /self\.params\.get\(\s*(['"])([A-Za-z_][\w]*)\1\s*,\s*([^)]+?)\s*\)/g;
  const out: ParamSpec[] = [];
  const seen = new Set<string>();
  let m: RegExpExecArray | null;
  while ((m = re.exec(code)) !== null) {
    const name = m[2];
    if (seen.has(name)) continue;
    seen.add(name);
    const rawDefault = m[3].trim();
    let kind: ParamSpec["kind"] = "string";
    let def = rawDefault;
    if (/^-?\d+(\.\d+)?$/.test(rawDefault)) kind = "number";
    else if (rawDefault === "True" || rawDefault === "False") {
      kind = "bool";
      def = rawDefault === "True" ? "true" : "false";
    } else if (
      (rawDefault.startsWith("'") && rawDefault.endsWith("'")) ||
      (rawDefault.startsWith('"') && rawDefault.endsWith('"'))
    ) {
      def = rawDefault.slice(1, -1);
    }
    out.push({ name, default: def, kind });
  }
  // Also catch bare `self.params["name"]` reads — these have no default
  // but still want a form field.
  const re2 = /self\.params\[\s*(['"])([A-Za-z_][\w]*)\1\s*\]/g;
  while ((m = re2.exec(code)) !== null) {
    const name = m[2];
    if (seen.has(name)) continue;
    seen.add(name);
    out.push({ name, default: "", kind: "string" });
  }
  return out;
}

/**
 * Convert a form-field string into a JSON-safe value matching the spec's
 * kind. Empty number stays as null so the strategy falls back to its
 * embedded default.
 */
function coerce(spec: ParamSpec, raw: string): unknown {
  if (raw.trim() === "") return null;
  if (spec.kind === "number") {
    const n = Number(raw);
    return Number.isFinite(n) ? n : raw;
  }
  if (spec.kind === "bool") return raw === "true" || raw === "True" || raw === "1";
  return raw;
}

/**
 * Build the params payload sent with /backtests POST. Drops nulls so the
 * server-side defaults (or the strategy's embedded defaults) win.
 */
export function buildParamsPayload(
  specs: ParamSpec[],
  values: Record<string, string>,
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const s of specs) {
    const v = coerce(s, values[s.name] ?? "");
    if (v !== null) out[s.name] = v;
  }
  return out;
}

export function ParamsForm({
  code,
  values,
  onChange,
}: {
  code: string;
  values: Record<string, string>;
  onChange: (next: Record<string, string>) => void;
}) {
  const specs = useMemo(() => extractParams(code), [code]);

  if (specs.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        No params detected. Add{" "}
        <code className="font-mono">self.params.get(&quot;name&quot;, default)</code> calls in the
        strategy to expose form fields here.
      </p>
    );
  }

  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {specs.map((s) => {
        const current = values[s.name] ?? s.default;
        return (
          <div key={s.name} className="space-y-1">
            <Label htmlFor={`p-${s.name}`} className="text-xs">
              {s.name}{" "}
              <span className="text-muted-foreground">
                ({s.kind}
                {s.default !== "" && `, default: ${s.default}`})
              </span>
            </Label>
            {s.kind === "bool" ? (
              <select
                id={`p-${s.name}`}
                value={current === "true" ? "true" : "false"}
                onChange={(e) => onChange({ ...values, [s.name]: e.target.value })}
                className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
              >
                <option value="false">false</option>
                <option value="true">true</option>
              </select>
            ) : (
              <Input
                id={`p-${s.name}`}
                value={current}
                inputMode={s.kind === "number" ? "decimal" : undefined}
                onChange={(e) => onChange({ ...values, [s.name]: e.target.value })}
                placeholder={s.default || "—"}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
