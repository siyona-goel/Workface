import { consoleData, faceName } from "@/lib/console-data";
import {
  HOUR_STATE_DOT,
  HOUR_STATE_LABEL,
  type HourState,
} from "@/lib/ribbon-data";
import { cn } from "@/lib/utils";

type Props = {
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  counts: Record<string, number>;
  faceHourState: Record<string, HourState>;
};

export function WorkFaceList({
  selectedId,
  onSelect,
  counts,
  faceHourState,
}: Props) {
  const groups = groupFaces();

  return (
    <aside className="flex h-full min-h-0 flex-col border-l border-border/70 bg-card/30">
      <div className="flex items-baseline justify-between px-3 py-2">
        <h2 className="text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
          Work faces
        </h2>
        <span className="font-mono text-[10px] text-muted-foreground">
          {consoleData.work_faces.length}
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-1.5 pb-3">
        {groups.map(([structure, faces]) => (
          <div key={structure} className="mb-2">
            <div className="sticky top-0 z-10 bg-background/90 px-2 py-1 text-[10px] font-semibold tracking-wider text-muted-foreground uppercase backdrop-blur">
              {structure}
            </div>
            <ul>
              {faces.map((face) => {
                const n = counts[face.id] ?? 0;
                const state = faceHourState[face.id] ?? "no_data";
                const selected = selectedId === face.id;
                const hero =
                  face.id === consoleData.hero_pair.bare ||
                  face.id === consoleData.hero_pair.shaded;
                return (
                  <li key={face.id}>
                    <button
                      type="button"
                      onClick={() => onSelect(selected ? null : face.id)}
                      title={HOUR_STATE_LABEL[state]}
                      className={cn(
                        "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors",
                        selected
                          ? "bg-primary/15 ring-1 ring-primary/40"
                          : "hover:bg-muted/40",
                        n === 0 && !selected && "opacity-45",
                      )}
                    >
                      <span
                        className={cn(
                          "size-1.5 shrink-0 rounded-full",
                          HOUR_STATE_DOT[state],
                        )}
                      />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[11px] text-foreground">
                          {faceName(face.id)}
                        </span>
                        <span className="block truncate font-mono text-[10px] text-muted-foreground">
                          {face.id}
                          {hero ? " · hero pair" : ""}
                        </span>
                      </span>
                      <span className="font-mono text-[10px] text-muted-foreground tabular-nums">
                        {n}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
    </aside>
  );
}

function groupFaces() {
  const map = new Map<string, typeof consoleData.work_faces>();
  for (const face of consoleData.work_faces) {
    const list = map.get(face.structure_id) ?? [];
    list.push(face);
    map.set(face.structure_id, list);
  }
  return [...map.entries()];
}
