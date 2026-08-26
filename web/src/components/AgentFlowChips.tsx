/**
 * AgentFlowChips — compact live "agent-flow" cards in the chat sidebar
 * (BL-2555). One card per delegate_task dispatch: header with status, goal,
 * agent count and a ticking clock; one row per subagent with its latest
 * real activity; frozen ✓/✗ receipts stay in the list after completion.
 *
 * Data source is the pure reducer over /api/events (`@/lib/agentFlows`) —
 * every state shown here mirrors an actual `subagent.*` frame from the
 * gateway; nothing is simulated. The clock is the only local animation.
 */

import { Card } from "@nous-research/ui/ui/components/card";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { useEffect, useState } from "react";

import {
  doneCount,
  formatClock,
  type AgentFlow,
  type AgentFlowRow,
} from "@/lib/agentFlows";

function StatusIcon({ state }: { state: AgentFlow["state"] }) {
  if (state === "running") {
    return <Loader2 className="size-4 shrink-0 animate-spin text-warning" />;
  }
  if (state === "done") {
    return <CheckCircle2 className="size-4 shrink-0 text-success" />;
  }
  return <XCircle className="size-4 shrink-0 text-destructive" />;
}

function RowLine({ row }: { row: AgentFlowRow }) {
  const fallback =
    row.state === "running" ? "kjører" : row.state === "done" ? "ferdig" : "feilet";
  return (
    <div className="flex items-center gap-2 text-xs" title={row.summary}>
      {row.state === "running" ? (
        <Loader2 className="size-3 shrink-0 animate-spin text-warning" />
      ) : row.state === "done" ? (
        <CheckCircle2 className="size-3 shrink-0 text-success" />
      ) : (
        <XCircle className="size-3 shrink-0 text-destructive" />
      )}
      <span className="shrink-0 font-mono text-text-secondary">a{row.index + 1}</span>
      <span className="min-w-0 flex-1 truncate text-text-tertiary">
        {row.activity ?? fallback}
      </span>
      {row.durationSeconds !== undefined && (
        <span className="shrink-0 font-mono text-xs tabular-nums text-text-tertiary">
          {formatClock(row.durationSeconds)}
        </span>
      )}
    </div>
  );
}

export function AgentFlowChips({ flows }: { flows: AgentFlow[] }) {
  // 1 Hz re-render while any flow is live so the header clock ticks; the
  // interval goes away as soon as the last chip freezes.
  const anyRunning = flows.some((f) => f.state === "running");
  // The tick carries the clock reading itself: reading Date.now() during
  // render is impure (react-hooks lint), so render consumes this state and
  // the interval refreshes it while anything runs.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!anyRunning) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [anyRunning]);

  if (flows.length === 0) return null;

  return (
    <>
      {flows.map((flow) => {
        // Clamped at 0: `now` only advances while something runs, so a flow
        // starting after an idle stretch is briefly newer than the last clock
        // reading. That window is under one tick (1s) and 0 is its truthful
        // floor — priming the clock inside the effect would fix it too, but
        // by trading this file's impure-render fix for a synchronous
        // setState-in-effect, which is the same rule from the other side.
        const elapsed = Math.max(0, (flow.endedAt ?? now) - flow.startedAt) / 1000;
        const done = doneCount(flow);
        const agents = Math.max(flow.taskCount, flow.rows.length);
        return (
          <Card key={flow.key} className="flex flex-col gap-2 px-3 py-2">
            <div className="flex items-center gap-2">
              <StatusIcon state={flow.state} />
              <div className="min-w-0 flex-1">
                <div className="text-display text-xs tracking-wider text-text-tertiary">
                  agent-flow · {agents} {agents === 1 ? "agent" : "agenter"}
                  {flow.nested > 0 && ` · +${flow.nested} nested`}
                </div>
                <div className="truncate text-sm font-medium" title={flow.goal}>
                  {flow.goal}
                </div>
              </div>
              <div className="shrink-0 text-right">
                <div
                  className={
                    flow.state === "running"
                      ? "font-mono text-xs tabular-nums text-warning"
                      : flow.state === "done"
                        ? "font-mono text-xs tabular-nums text-success"
                        : "font-mono text-xs tabular-nums text-destructive"
                  }
                >
                  {formatClock(elapsed)}
                </div>
                {flow.state === "running" && (
                  <div className="text-xs tabular-nums text-text-tertiary">
                    {done}/{flow.taskCount}
                  </div>
                )}
              </div>
            </div>
            {flow.rows.length > 0 && (
              <div className="flex flex-col gap-1">
                {flow.rows
                  .slice()
                  .sort((a, b) => a.index - b.index)
                  .map((row) => (
                    <RowLine key={row.id} row={row} />
                  ))}
              </div>
            )}
          </Card>
        );
      })}
    </>
  );
}
