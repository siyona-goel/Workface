"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { cn } from "@/lib/utils";

type NavId = "console" | "trace" | "conflicts" | "escalate" | "brief";

type Props = {
  current: NavId;
};

const items: { href: string; id: NavId; label: string }[] = [
  { href: "/", id: "console", label: "Console" },
  { href: "/trace", id: "trace", label: "Trace" },
  { href: "/conflicts", id: "conflicts", label: "Conflicts" },
  { href: "/escalate", id: "escalate", label: "Escalate" },
  { href: "/brief", id: "brief", label: "Brief" },
];

export function AppNav({ current }: Props) {
  const params = useSearchParams();
  const src = params.get("src");

  return (
    <nav className="flex items-center gap-0.5 rounded-md border border-border/70 p-0.5">
      {items.map((item) => {
        const href =
          src && item.href !== "/"
            ? `${item.href}?src=${src}`
            : item.href;
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
