import { DashboardOverview } from "@/components/dashboard/overview";
import { SetupChecklist } from "@/components/dashboard/setup-checklist";

export default function Dashboard() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          Equity, today&apos;s P&amp;L, running strategies, and recent fills + signals at a glance.
        </p>
      </header>

      <SetupChecklist />
      <DashboardOverview />
    </div>
  );
}
