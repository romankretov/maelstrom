"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  Bell,
  FlaskConical,
  HeartPulse,
  LayoutDashboard,
  LineChart,
  MessageSquareText,
  Radio,
  Settings,
  Signal,
  Wallet,
} from "lucide-react";
import { AccountSwitcher } from "@/components/account-switcher";
import { cn } from "@/lib/utils";

const ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/markets", label: "Markets", icon: LineChart },
  { href: "/research", label: "Research", icon: FlaskConical },
  { href: "/strategies", label: "Strategies", icon: Activity },
  { href: "/live", label: "Live runs", icon: Radio },
  { href: "/portfolio", label: "Portfolio", icon: Wallet },
  { href: "/signals", label: "Signals", icon: Signal },
  { href: "/alerts", label: "Alerts", icon: Bell },
  { href: "/journal", label: "Journal", icon: MessageSquareText },
  { href: "/health", label: "Health", icon: HeartPulse },
  { href: "/settings", label: "Settings", icon: Settings },
] as const;

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="hidden w-56 shrink-0 flex-col border-r bg-card md:flex">
      <div className="px-5 py-6">
        <Link href="/dashboard" className="text-lg font-semibold">
          Maelstrom
        </Link>
      </div>
      <nav className="flex-1 space-y-1 px-2">
        {ITEMS.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(href + "/");
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-secondary text-secondary-foreground"
                  : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          );
        })}
      </nav>
      <div className="pb-4 pt-3">
        <AccountSwitcher />
      </div>
    </aside>
  );
}
