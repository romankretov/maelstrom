import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function Dashboard() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="text-sm text-muted-foreground">Phase 0 scaffold — real widgets land in Phase 4.</p>
      </header>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {["Equity", "Today P&L", "Open positions", "Active strategies"].map((label) => (
          <Card key={label}>
            <CardHeader><CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle></CardHeader>
            <CardContent className="text-2xl font-semibold tabular-nums">—</CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
