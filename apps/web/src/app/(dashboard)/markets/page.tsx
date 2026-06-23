"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { Source, Timeframe } from "@/lib/markets";
import { InstrumentList } from "@/components/markets/instrument-list";
import { ChartPanel } from "@/components/markets/chart-panel";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export default function MarketsPage() {
  const { data: sources } = useSWR<Source[]>("/markets/sources", fetcher);
  const [source, setSource] = useState<string>("binance");
  const [symbol, setSymbol] = useState<string | null>(null);
  const [timeframe, setTimeframe] = useState<Timeframe>("1h");

  return (
    <div className="flex h-[calc(100vh-3rem)] flex-col gap-4">
      <header className="flex items-baseline justify-between gap-4">
        <h1 className="text-2xl font-semibold">Markets</h1>
        <div className="flex gap-1">
          {sources?.map((s) => (
            <Button
              key={s.name}
              variant={s.name === source ? "default" : "ghost"}
              size="sm"
              className={cn("h-8", s.name !== source && "text-muted-foreground")}
              onClick={() => {
                setSource(s.name);
                setSymbol(null);
              }}
            >
              {s.label}
            </Button>
          ))}
        </div>
      </header>
      <div className="grid flex-1 grid-cols-1 gap-4 overflow-hidden lg:grid-cols-[260px_1fr]">
        <aside className="hidden h-full overflow-hidden lg:block">
          <InstrumentList source={source} selected={symbol} onSelect={setSymbol} />
        </aside>
        <section className="overflow-hidden">
          <ChartPanel
            source={source}
            symbol={symbol}
            timeframe={timeframe}
            onTimeframe={setTimeframe}
          />
        </section>
      </div>
      {/* Mobile instrument picker shown below chart */}
      <div className="block lg:hidden">
        <InstrumentList source={source} selected={symbol} onSelect={setSymbol} />
      </div>
    </div>
  );
}
