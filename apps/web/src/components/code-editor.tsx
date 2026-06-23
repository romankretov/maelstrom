"use client";

import dynamic from "next/dynamic";

// Monaco is a large client-side module; load it only in the browser.
const Editor = dynamic(() => import("@monaco-editor/react").then((m) => m.Editor), {
  ssr: false,
  loading: () => (
    <div className="grid h-72 place-items-center rounded-md border bg-card text-sm text-muted-foreground">
      Loading editor…
    </div>
  ),
});

export function CodeEditor({
  value,
  onChange,
  height = 480,
  language = "python",
  readOnly = false,
}: {
  value: string;
  onChange: (next: string) => void;
  height?: number;
  language?: "python" | "json";
  readOnly?: boolean;
}) {
  return (
    <div className="overflow-hidden rounded-md border">
      <Editor
        height={height}
        defaultLanguage={language}
        theme="vs-dark"
        value={value}
        onChange={(v) => onChange(v ?? "")}
        options={{
          readOnly,
          fontSize: 13,
          fontFamily: "ui-monospace, SFMono-Regular, monospace",
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          tabSize: 4,
          insertSpaces: true,
          wordWrap: "off",
          renderLineHighlight: "all",
          smoothScrolling: true,
        }}
      />
    </div>
  );
}
