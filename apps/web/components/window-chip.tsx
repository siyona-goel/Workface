import { cn } from "@/lib/utils";
import { VERDICT_LABEL, type Verdict } from "@/lib/console-data";
import { VERDICT_CHIP, VERDICT_DOT } from "@/lib/verdicts";

type Props = {
  verdict: Verdict;
  count?: number;
  pressed?: boolean;
  onToggle?: () => void;
  static?: boolean;
};

export function WindowChip({
  verdict,
  count,
  pressed = false,
  onToggle,
  static: isStatic,
}: Props) {
  const className = cn(
    "inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-1 text-[11px] font-medium tracking-wide transition-colors",
    VERDICT_CHIP[verdict],
    !isStatic && "hover:brightness-110",
  );

  const inner = (
    <>
      <span className={cn("size-1.5 shrink-0 rounded-full", VERDICT_DOT[verdict])} />
      <span className="whitespace-nowrap">{VERDICT_LABEL[verdict]}</span>
      {count != null ? (
        <span className="min-w-[2ch] font-mono text-[10px] tabular-nums opacity-70">
          {count}
        </span>
      ) : null}
    </>
  );

  if (isStatic || !onToggle) {
    return <span className={className}>{inner}</span>;
  }

  return (
    <button
      type="button"
      data-on={pressed}
      aria-pressed={pressed}
      onClick={onToggle}
      className={cn(className, !pressed && "opacity-55 hover:opacity-90")}
    >
      {inner}
    </button>
  );
}
