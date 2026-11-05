"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { num, useT } from "@/lib/i18n";

type Arrow = [number, number, number, number];

/** Draw "traffic goes this way" arrows on a frame. Arrows are reported in analysis-frame pixels
 *  (long side scaled to 1280, as the pipeline does). */
export default function ArrowCanvas({
  frame,
  arrows,
  onChange,
}: {
  frame: ImageBitmap | null;
  arrows: Arrow[];
  onChange: (a: Arrow[]) => void;
}) {
  const { t, lang } = useT();
  const ref = useRef<HTMLCanvasElement>(null);
  const [drag, setDrag] = useState<{ x: number; y: number; x2: number; y2: number } | null>(null);
  const scale = frame ? Math.min(1, 1280 / Math.max(frame.width, frame.height)) : 1;

  const draw = useCallback(() => {
    const c = ref.current;
    if (!c || !frame) return;
    const g = c.getContext("2d")!;
    g.drawImage(frame, 0, 0);
    const lw = Math.max(4, c.width / 200);
    const all: Arrow[] = arrows.map((a) => a.map((v) => v / scale) as Arrow);
    if (drag) all.push([drag.x, drag.y, drag.x2, drag.y2]);
    for (const [x1, y1, x2, y2] of all) {
      g.strokeStyle = "#00e676";
      g.fillStyle = "#00e676";
      g.lineWidth = lw;
      g.beginPath();
      g.moveTo(x1, y1);
      g.lineTo(x2, y2);
      g.stroke();
      const ang = Math.atan2(y2 - y1, x2 - x1);
      const L = lw * 5;
      g.beginPath();
      g.moveTo(x2, y2);
      g.lineTo(x2 - L * Math.cos(ang - 0.45), y2 - L * Math.sin(ang - 0.45));
      g.lineTo(x2 - L * Math.cos(ang + 0.45), y2 - L * Math.sin(ang + 0.45));
      g.closePath();
      g.fill();
    }
  }, [frame, arrows, drag, scale]);

  useEffect(() => {
    const c = ref.current;
    if (c && frame) {
      c.width = frame.width;
      c.height = frame.height;
    }
    draw();
  }, [frame, draw]);

  const pos = (e: React.PointerEvent) => {
    const c = ref.current!;
    const r = c.getBoundingClientRect();
    return { x: ((e.clientX - r.left) * c.width) / r.width, y: ((e.clientY - r.top) * c.height) / r.height };
  };

  if (!frame) return null;
  return (
    <div className="space-y-2">
      <canvas
        ref={ref}
        className="w-full max-h-[60vh] object-contain rounded-lg touch-none cursor-crosshair bg-black"
        aria-label={t("arrowsHint")}
        onPointerDown={(e) => {
          (e.target as HTMLCanvasElement).setPointerCapture(e.pointerId);
          const p = pos(e);
          setDrag({ x: p.x, y: p.y, x2: p.x, y2: p.y });
        }}
        onPointerMove={(e) => drag && setDrag({ ...drag, ...{ x2: pos(e).x, y2: pos(e).y } })}
        onPointerUp={() => {
          if (drag && Math.hypot(drag.x2 - drag.x, drag.y2 - drag.y) > frame.width / 30) {
            onChange([...arrows, [drag.x, drag.y, drag.x2, drag.y2].map((v) => Math.round(v * scale)) as Arrow]);
          }
          setDrag(null);
        }}
      />
      <div className="flex items-center gap-3 text-sm">
        <span>
          {num(arrows.length, lang)} {t("arrowsCount")}
        </span>
        <button type="button" className="btn-secondary" onClick={() => onChange([])} disabled={!arrows.length}>
          {t("clearArrows")}
        </button>
      </div>
    </div>
  );
}
