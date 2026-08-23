"use client";

import Link from "next/link";

import { cn } from "@/lib/utils";

type Props = {
  current: "console" | "trace";
};

const items = [
  { href: "/", id: "console" as const, label: "Console" },
  { href: "/trace", id: "trace" as const, label: "Trace" },
];

export function AppNav({ current }: Props) {
  return (
    <nav className="flex items-center gap-0.5 rounded-md border border-border/70 p-0.5">
      {items.map((item) => (
        <Link
          key={item.id}
          href={item.href}
          className={cn(
            "rounded-sm px-2 py-0.5 text-[11px] font-medium tracking-wide",
            current === item.id
              ? "bg-muted text-foreground"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {item.label}
        </Link>
      ))}
    </nav>
  );
}
