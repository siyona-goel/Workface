"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { cn } from "@/lib/utils";

type NavId = "console" | "trace" | "conflicts" | "escalate" | "brief" | "record";

type Props = {
  current: NavId;
};

const items: { href: string; id: NavId; label: string }[] = [
  { href: "/", id: "console", label: "Console" },
  { href: "/trace", id: "trace", label: "Trace" },
  { href: "/conflicts", id: "conflicts", label: "Conflicts" },
  { href: "/escalate", id: "escalate", label: "Escalate" },
  { href: "/brief", id: "brief", label: "Brief" },
  { href: "/record", id: "record", label: "Record" },
];

export function AppNav({ current }: Props) {
  const params = useSearchParams();
  const src = params.get("src");
  const debug = params.get("debug");

  return (
    <nav className="flex items-center gap-0.5 rounded-md border border-border/70 p-0.5">
      {items.map((item) => {
        const next = new URLSearchParams();
        if (src) next.set("src", src);
        if (debug) next.set("debug", debug);
        const qs = next.toString();
        const href =
          qs && item.href !== "/" ? `${item.href}?${qs}` : item.href;
        return (
          <Link
            key={item.id}
            href={href}
            className={cn(
              "rounded-sm px-2 py-0.5 text-[11px] font-medium tracking-wide",
              current === item.id
                ? "bg-muted text-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
