"use client";

import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { morningBrief } from "@/lib/morning-brief";
import {
  CHANNEL_LABEL,
  notificationTemplates,
  renderNotification,
  templateById,
  type NotificationChannel,
  type NotificationTemplate,
} from "@/lib/notification-templates";
import { cn } from "@/lib/utils";

function VarsList({ vars }: { vars: Record<string, string> }) {
  return (
    <div className="rounded-lg border border-border/70 bg-card/40 px-3 py-2.5">
      <p className="text-[10px] font-medium tracking-[0.14em] text-muted-foreground uppercase">
        Sample vars
      </p>
      <dl className="mt-2 space-y-1.5">
        {Object.entries(vars).map(([key, value]) => (
          <div
            key={key}
            className="grid grid-cols-[minmax(0,8rem)_1fr] items-baseline gap-2"
          >
            <dt className="font-mono text-[10px] text-muted-foreground">
              {`{{${key}}}`}
            </dt>
            <dd className="min-w-0 text-[12px] leading-snug">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function TemplatePreview({
  template,
  vars,
}: {
  template: NotificationTemplate;
  vars: Record<string, string>;
}) {
  const rendered = useMemo(
    () => renderNotification(template, vars),
    [template, vars],
  );

  async function copyBody() {
    await navigator.clipboard.writeText(rendered.body);
  }

  return (
    <div className="flex min-h-0 flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-sm border border-border/70 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
          {template.id}
        </span>
        <span className="text-[10px] text-muted-foreground">
          {template.tool}
          {template.gated ? " · gated" : null}
        </span>
        <span
          className={cn(
            "ml-auto font-mono text-[10px]",
            rendered.overLimit ? "text-red-300" : "text-muted-foreground",
          )}
        >
          {rendered.length}/{template.max_length} chars
        </span>
      </div>

      <div className="rounded-lg border border-border/70 bg-card/40 px-3 py-2.5">
        <p className="text-[10px] font-medium tracking-[0.14em] text-muted-foreground uppercase">
          Subject
        </p>
        <p className="mt-1 text-[13px] font-medium">{rendered.subject}</p>
      </div>

      <div className="rounded-lg border border-border/70 bg-zinc-950/80 px-3 py-3">
        <p className="text-[10px] font-medium tracking-[0.14em] text-muted-foreground uppercase">
          Body
        </p>
        <p className="mt-2 font-mono text-[12px] leading-relaxed whitespace-pre-wrap">
          {rendered.body}
        </p>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {template.channels.map((ch) => (
          <span
            key={ch}
            className="rounded-sm border border-border/60 px-1.5 py-0.5 text-[10px] text-muted-foreground"
          >
            {CHANNEL_LABEL[ch as NotificationChannel]}
          </span>
        ))}
      </div>

      <Button variant="outline" size="xs" onClick={() => void copyBody()}>
        Copy body
      </Button>
    </div>
  );
}

export function NotificationTemplatesPanel() {
  const [selectedId, setSelectedId] = useState(notificationTemplates[0]?.id ?? "");
  const [useQueue, setUseQueue] = useState(true);

  const selected = templateById(selectedId) ?? notificationTemplates[0]!;
  const queueMatch = morningBrief.notification_queue.find(
    (n) => n.template_id === selectedId,
  );

  const vars = useQueue && queueMatch ? queueMatch.vars : selected.sample_vars;

  return (
    <section className="flex min-h-0 flex-col">
      <div className="mb-3">
        <h2 className="text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
          Notification templates
        </h2>
        <p className="mt-1 text-[12px] text-muted-foreground">
          Gated <span className="font-mono">notify_crew</span> messages for
          today&apos;s brief. Preview uses the queued vars when available.
        </p>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-3 lg:grid lg:grid-cols-[minmax(180px,220px)_minmax(0,1fr)]">
        <ul className="flex gap-1.5 overflow-x-auto pb-1 lg:flex-col lg:overflow-x-visible lg:pb-0">
          {notificationTemplates.map((t) => (
            <li key={t.id} className="min-w-[180px] lg:min-w-0">
              <button
                type="button"
                onClick={() => setSelectedId(t.id)}
                className={cn(
                  "w-full rounded-lg border px-2.5 py-2 text-left text-[12px] transition-colors",
                  selectedId === t.id
                    ? "border-border bg-muted/50 text-foreground"
                    : "border-transparent text-muted-foreground hover:border-border/60 hover:bg-muted/20",
                )}
              >
                <span className="block font-medium">{t.label}</span>
                <span className="mt-0.5 block font-mono text-[10px] opacity-70">
                  {t.id}
                </span>
              </button>
            </li>
          ))}
        </ul>

        <div className="min-h-0 rounded-xl border border-border/70 bg-background/40 p-3 sm:p-4">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-0.5 rounded-md border border-border/70 p-0.5">
              <button
                type="button"
                aria-pressed={useQueue}
                onClick={() => setUseQueue(true)}
                className={cn(
                  "rounded-sm px-2 py-0.5 text-[11px] font-medium",
                  useQueue
                    ? "bg-muted text-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                Brief queue
              </button>
              <button
                type="button"
                aria-pressed={!useQueue}
                onClick={() => setUseQueue(false)}
                className={cn(
                  "rounded-sm px-2 py-0.5 text-[11px] font-medium",
                  !useQueue
                    ? "bg-muted text-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                Sample vars
              </button>
            </div>
            {useQueue && queueMatch ? (
              <span className="text-[10px] text-muted-foreground">
                {queueMatch.activity_id} · {queueMatch.channel} ·{" "}
                {queueMatch.status}
              </span>
            ) : useQueue ? (
              <span className="text-[10px] text-muted-foreground">
                No queued message for this template today
              </span>
            ) : (
              <span className="text-[10px] text-muted-foreground">
                Catalog fill · {Object.keys(selected.sample_vars).length} vars
              </span>
            )}
          </div>

          {useQueue && !queueMatch ? (
            <p className="rounded-lg border border-dashed border-border/70 px-3 py-6 text-center text-[13px] text-muted-foreground">
              Nothing in today&apos;s brief queue for this template. Open
              Sample vars to preview the catalog fill.
            </p>
          ) : (
            <div className="flex min-h-0 flex-col gap-3">
              {!useQueue ? <VarsList vars={selected.sample_vars} /> : null}
              <TemplatePreview template={selected} vars={vars} />
            </div>
          )}

          <details className="mt-4 border-t border-border/60 pt-3">
            <summary className="cursor-pointer text-[11px] text-muted-foreground">
              Template source
            </summary>
            <pre className="mt-2 overflow-x-auto rounded-md bg-zinc-950/60 p-2 font-mono text-[10px] leading-relaxed text-muted-foreground">
              {selected.body}
            </pre>
          </details>
        </div>
      </div>
    </section>
  );
}
