"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { Source, Timeframe } from "@/lib/markets";
import { InstrumentList } from "@/components/markets/instrument-list";
import { StatsCard } from "@/components/research/stats-card";
import { FundingChart } from "@/components/research/funding-chart";
import { CorrelationMatrix } from "@/components/research/correlation-matrix";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export default function ResearchPage() {
  const { data: sources } = useSWR<Source[]>("/markets/sources", fetcher);
  const [source, setSource] = useState<string>("binance");
  const [symbol, setSymbol] = useState<string | null>(null);
  const [timeframe, setTimeframe] = useState<Timeframe>("1h");

  return (
    <div className="flex flex-col gap-4">
      <header className="flex items-baseline justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Research</h1>
          <p className="text-sm text-muted-foreground">
            Symbol stats, funding rate history, correlation across instruments.
          </p>
        </div>
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

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[260px_1fr]">
        <aside className="lg:max-h-[640px]">
          <InstrumentList source={source} selected={symbol} onSelect={setSymbol} />
        </aside>
        <section className="flex flex-col gap-4">
          <StatsCard
            source={source}
            symbol={symbol}
            timeframe={timeframe}
            onTimeframe={setTimeframe}
          />
          <FundingChart source={source} symbol={symbol} />
          <CorrelationMatrix source={source} />
        </section>
      </div>
    </div>
  );
}
