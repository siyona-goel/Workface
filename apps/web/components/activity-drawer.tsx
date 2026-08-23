"use client";

import { useEffect } from "react";
import { X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { CureFitChart } from "@/components/cure-fit-chart";
import { ThermalChart } from "@/components/thermal-chart";
import { WindowChip } from "@/components/window-chip";
import {
  consoleData,
  evalFor,
  formatUsd,
  formatWhen,
} from "@/lib/console-data";
import { ribbonEvalFor, type RibbonEval } from "@/lib/ribbon-data";

type Props = {
  activityId: string | null;
  open: boolean;
  onClose: () => void;
};

export function ActivityDrawer({ activityId, open, onClose }: Props) {
  const evaluation = activityId ? ribbonEvalFor(activityId) : undefined;
  const activity = activityId
    ? consoleData.activities.find((a) => a.id === activityId)
    : undefined;

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open || !activityId) return null;

  const title =
    evaluation?.activity_name ?? activity?.name ?? "Activity detail";

  return (
    <>
      <button
        type="button"
        aria-label="Close activity detail"
        className="fixed inset-0 z-[55] bg-black/40"
        onClick={onClose}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="activity-drawer-title"
        className="fixed inset-y-0 right-0 z-[60] flex w-full max-w-full flex-col border-l border-border bg-background shadow-2xl sm:max-w-lg"
      >
        <header className="flex items-start justify-between gap-3 border-b border-border/70 px-4 py-3">
          <div className="min-w-0">
            <p className="font-mono text-[10px] text-muted-foreground">
              {activityId}
            </p>
            <h2
              id="activity-drawer-title"
              className="truncate text-sm font-semibold"
            >
              {title}
            </h2>
            {evaluation ? (
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <WindowChip verdict={evaluation.verdict} static />
                <span className="truncate text-[11px] text-muted-foreground">
                  {evaluation.work_face_name}
                </span>
              </div>
            ) : null}
          </div>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Close"
            onClick={onClose}
          >
            <X />
          </Button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
          {evaluation ? (
            <DrawerBody evaluation={evaluation} />
          ) : (
            <p className="py-10 text-center text-sm text-muted-foreground">
              No window_eval for this activity. Pick a ribbon lane to open a
              thermal detail.
            </p>
          )}
        </div>
      </aside>
    </>
  );
}

function DrawerBody({ evaluation }: { evaluation: RibbonEval }) {
  const offset = evaluation.constraints?.find((c) => c.type === "offset");
  const hasCure = evaluation.constraints?.some((c) => c.type === "cure_clock");
  const cited =
    offset ??
    evaluation.constraints?.find(
      (c) => c.type === evaluation.binding_constraint?.type,
    );
  const exposure = evalFor(evaluation.activity_id)?.usd_exposure;
  const delta = evaluation.offset_delta_c;

  return (
    <div className="flex flex-col gap-5">
      <p className="text-[12px] leading-relaxed text-muted-foreground">
        {evaluation.verdict_summary}
      </p>
      <p className="font-mono text-[10px] text-muted-foreground">
        {formatWhen(evaluation.scheduled.start)} –{" "}
        {formatWhen(evaluation.scheduled.finish)} · {evaluation.trade_display_name}
      </p>

      <section>
        <h3 className="text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
          T_air · T_surf · T_dew
        </h3>
        <p className="mb-2 text-[11px] text-muted-foreground">
          {delta != null && delta > 0
            ? `Pastel band is dew point + ${delta} °C${delta === 2.8 ? " (5 °F)" : ""}. T_surf must sit above it.`
            : delta === 0
              ? "Offset is 0 °C on this trade — no 5 °F band to draw."
              : "This trade has no dew-point offset constraint."}
        </p>
        <ThermalChart evaluation={evaluation} />
      </section>

      <section>
        <h3 className="text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
          Cited clause
        </h3>
        {cited ? (
          <blockquote className="mt-2 border-l-2 border-amber-300/50 pl-3 text-[12px] leading-relaxed text-foreground/90">
            {cited.citation_fragment}
          </blockquote>
        ) : null}
        {evaluation.citation ? (
          <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
            {evaluation.citation}
          </p>
        ) : null}
        {evaluation.standard_ref ? (
          <p className="mt-1 font-mono text-[10px] text-muted-foreground">
            {evaluation.standard_ref}
          </p>
        ) : null}
      </section>

      {hasCure ? (
        <section>
          <h3 className="text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
            Cure-fit · Macropoxy 646
          </h3>
          <p className="mb-2 text-[11px] text-muted-foreground">
            Hours to service vs substrate temperature. Gold dots are the PDS
            table; the green line is the piecewise Q10 fit.
          </p>
          <CureFitChart />
        </section>
      ) : (
        <section>
          <h3 className="text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
            Cure-fit
          </h3>
          <p className="mt-2 text-[12px] text-muted-foreground">
            No cure-clock on this trade. The Macropoxy Q10 plot is shown on
            coating activities.
          </p>
        </section>
      )}

      {evaluation.binding_constraint ? (
        <section>
          <h3 className="text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
            Binding constraint
          </h3>
          <p className="mt-1 text-[12px]">{evaluation.binding_constraint.label}</p>
          {evaluation.binding_constraint.mitigation_hint ? (
            <p className="mt-1 text-[11px] text-muted-foreground">
              {evaluation.binding_constraint.mitigation_hint}
            </p>
          ) : null}
        </section>
      ) : null}

      <p className="border-t border-border/60 pt-3 text-[10px] leading-snug text-muted-foreground">
        {evaluation.advisory_notice ??
          "Advisory and contractual. Does not replace the field measurement the referenced standard requires."}
        {exposure && exposure.at_risk_usd > 0
          ? ` · ${formatUsd(exposure.at_risk_usd)} at risk`
          : null}
      </p>
    </div>
  );
}
