import Link from "next/link";

import { recordMeta } from "@/lib/record-data";

export function HeatIntelligenceEmbed() {
  const hi = recordMeta.heat_intelligence;

  return (
    <section className="rounded-xl border border-border/70 bg-card/20 p-4 sm:p-5">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
            Heat intelligence
          </h2>
          <h3 className="mt-1 text-base font-semibold">{hi.title}</h3>
          <p className="mt-1 text-[12px] text-muted-foreground">
            {hi.activity_name} · {hi.work_face_name}
          </p>
          <p className="mt-1 font-mono text-[10px] text-muted-foreground">
            fg {hi.fg_activity_id} · {hi.source_date} · {hi.temperature_c} °C
            mean ({hi.temperature_source})
          </p>
        </div>
        <Link
          href={hi.pdf_url}
          target="_blank"
          rel="noopener noreferrer"
          className="rounded-md border border-border/70 px-2.5 py-1 text-[11px] font-medium hover:bg-muted/30"
        >
          Open PDF
        </Link>
      </div>

      <div className="overflow-hidden rounded-lg border border-border/80 bg-zinc-950">
        <iframe
          title={hi.title}
          src={hi.pdf_url}
          className="h-[min(720px,70dvh)] w-full"
        />
      </div>

      <p className="mt-3 text-[11px] leading-relaxed text-muted-foreground">
        {hi.note}
      </p>
    </section>
  );
}
