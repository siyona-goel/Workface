import { WindowChip } from "@/components/window-chip";
import {
  evalFor,
  faceName,
  formatFloat,
  formatHours,
  formatUsd,
  formatWhen,
  tradeShort,
  verdictOf,
  type Activity,
} from "@/lib/console-data";
import { cn } from "@/lib/utils";

type Props = {
  activities: Activity[];
  selectedId: string | null;
  onSelect: (activity: Activity) => void;
};

export function ActivityTable({ activities, selectedId, onSelect }: Props) {
  return (
    <div className="flex h-full min-h-0 flex-col bg-card/20">
      <div className="flex items-baseline justify-between gap-2 px-3 py-2 sm:px-4">
        <h2 className="text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
          Activities
        </h2>
        <p className="truncate text-[10px] text-muted-foreground">
          {activities.length} in view
          <span className="hidden sm:inline">
            {" "}
            · click a row to open the detail drawer
          </span>
        </p>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full min-w-[520px] border-collapse text-left text-[12px] lg:min-w-[960px]">
          <thead className="sticky top-0 z-10 bg-background/95 text-[10px] font-medium tracking-wider text-muted-foreground uppercase backdrop-blur">
            <tr className="border-b border-border/70">
              <th className="px-3 py-2 font-medium">ID</th>
              <th className="px-3 py-2 font-medium">Activity</th>
              <th className="hidden px-3 py-2 font-medium md:table-cell">
                Trade
              </th>
              <th className="hidden px-3 py-2 font-medium lg:table-cell">
                Work face
              </th>
              <th className="hidden px-3 py-2 font-medium md:table-cell">
                Planned
              </th>
              <th className="hidden px-3 py-2 font-medium sm:table-cell">
                Dur
              </th>
              <th className="hidden px-3 py-2 font-medium lg:table-cell">
                Float
              </th>
              <th className="px-3 py-2 font-medium">Window</th>
              <th className="px-3 py-2 text-right font-medium">$ at risk</th>
            </tr>
          </thead>
          <tbody>
            {activities.length === 0 ? (
              <tr>
                <td
                  colSpan={9}
                  className="px-3 py-10 text-center text-muted-foreground"
                >
                  No activities match the current filters.
                </td>
              </tr>
            ) : (
              activities.map((a) => {
                const ev = evalFor(a.id);
                const verdict = verdictOf(a);
                const selected = selectedId === a.id;
                return (
                  <tr
                    key={a.id}
                    onClick={() => onSelect(a)}
                    className={cn(
                      "cursor-pointer border-b border-border/40 transition-colors",
                      selected
                        ? "bg-primary/15"
                        : "hover:bg-muted/30",
                    )}
                  >
                    <td className="px-3 py-2 align-top font-mono text-[11px] text-muted-foreground">
                      {a.id}
                    </td>
                    <td className="max-w-[280px] px-3 py-2 align-top">
                      <div className="truncate font-medium text-foreground">
                        {a.name}
                      </div>
                      <div className="mt-0.5 flex flex-wrap gap-1.5 font-mono text-[10px] text-muted-foreground">
                        <span>{a.wbs}</span>
                        {a.is_critical ? (
                          <span className="text-red-300">critical</span>
                        ) : a.is_near_critical ? (
                          <span className="text-amber-300">near-crit</span>
                        ) : null}
                        {a.hold_point ? (
                          <span className="text-sky-300">hold</span>
                        ) : null}
                      </div>
                    </td>
                    <td
                      className="hidden max-w-[160px] truncate px-3 py-2 align-top text-muted-foreground md:table-cell"
                      title={ev?.trade_display_name ?? tradeShort(a.trade_id)}
                    >
                      {tradeShort(a.trade_id)}
                    </td>
                    <td
                      className="hidden max-w-[180px] truncate px-3 py-2 align-top text-muted-foreground lg:table-cell"
                      title={faceName(a.work_face_id)}
                    >
                      {faceName(a.work_face_id)}
                    </td>
                    <td className="hidden whitespace-nowrap px-3 py-2 align-top font-mono text-[11px] text-muted-foreground md:table-cell">
                      {formatWhen(a.planned_start)}
                      <span className="block text-[10px] opacity-70">
                        → {formatWhen(a.planned_finish)}
                      </span>
                    </td>
                    <td className="hidden px-3 py-2 align-top font-mono text-[11px] text-muted-foreground sm:table-cell">
                      {formatHours(a.duration_h)}
                    </td>
                    <td
                      className={cn(
                        "hidden px-3 py-2 align-top font-mono text-[11px] lg:table-cell",
                        a.total_float_d === 0
                          ? "text-red-300"
                          : "text-muted-foreground",
                      )}
                    >
                      {formatFloat(a.total_float_d)}d
                    </td>
                    <td className="px-3 py-2 align-top">
                      <WindowChip verdict={verdict} static />
                      {ev?.binding_constraint ? (
                        <div
                          className="mt-1 max-w-[200px] truncate text-[10px] text-muted-foreground"
                          title={ev.verdict_summary}
                        >
                          {ev.binding_constraint.label}
                        </div>
                      ) : null}
                    </td>
                    <td className="px-3 py-2 text-right align-top font-mono text-[11px] text-muted-foreground">
                      {formatUsd(ev?.usd_exposure.at_risk_usd ?? 0)}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
