"use client";

import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

type Props = {
  label: string;
  onResize: (clientY: number) => void;
  onDragChange?: (dragging: boolean) => void;
};

export function RowResizeHandle({ label, onResize, onDragChange }: Props) {
  const draggingRef = useRef(false);
  const onResizeRef = useRef(onResize);
  const onDragChangeRef = useRef(onDragChange);
  onResizeRef.current = onResize;
  onDragChangeRef.current = onDragChange;

  useEffect(() => {
    function stopDrag() {
      if (!draggingRef.current) return;
      draggingRef.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      onDragChangeRef.current?.(false);
    }

    function onMove(event: PointerEvent) {
      if (!draggingRef.current) return;
      onResizeRef.current(event.clientY);
    }

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", stopDrag);
    window.addEventListener("pointercancel", stopDrag);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", stopDrag);
      window.removeEventListener("pointercancel", stopDrag);
    };
  }, []);

  return (
    <div
      role="separator"
      aria-orientation="horizontal"
      aria-label={label}
      tabIndex={0}
      onPointerDown={(event) => {
        event.preventDefault();
        draggingRef.current = true;
        document.body.style.cursor = "row-resize";
        document.body.style.userSelect = "none";
        onDragChangeRef.current?.(true);
        onResizeRef.current(event.clientY);
      }}
      className={cn(
        "group relative z-20 flex h-2 shrink-0 cursor-row-resize items-center justify-center",
        "touch-none select-none outline-none after:absolute after:-inset-y-1.5 after:inset-x-0",
      )}
    >
      <div className="h-px w-full bg-border/70" />
      <div
        className={cn(
          "absolute h-1 w-9 rounded-full bg-muted-foreground/35",
          "opacity-70 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100",
          "group-active:bg-foreground/60 group-hover:bg-muted-foreground/70",
        )}
      />
    </div>
  );
}
