"use client";

import { useEffect, useRef } from "react";
import type { HeatmapCell } from "../lib/heatmapViewModel";

type HeatmapCanvasProps = {
  cells: HeatmapCell[];
  width: number;
  height: number;
};

function colorStop(intensity: number, alphaScale: number) {
  if (intensity > 0.86) return `rgba(240, 255, 42, ${0.76 * alphaScale})`;
  if (intensity > 0.68) return `rgba(115, 232, 64, ${0.58 * alphaScale})`;
  if (intensity > 0.5) return `rgba(38, 210, 172, ${0.43 * alphaScale})`;
  if (intensity > 0.32) return `rgba(45, 134, 196, ${0.3 * alphaScale})`;
  return `rgba(55, 66, 142, ${0.18 * alphaScale})`;
}

export function HeatmapCanvas({ cells, width, height }: HeatmapCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context || width <= 0 || height <= 0) {
      return;
    }

    const pixelRatio = window.devicePixelRatio || 1;
    canvas.width = Math.round(width * pixelRatio);
    canvas.height = Math.round(height * pixelRatio);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
    context.clearRect(0, 0, width, height);

    const base = context.createLinearGradient(0, 0, width, height);
    base.addColorStop(0, "#0a1220");
    base.addColorStop(0.44, "#08111b");
    base.addColorStop(1, "#04070d");
    context.fillStyle = base;
    context.fillRect(0, 0, width, height);

    context.globalCompositeOperation = "lighter";
    for (const cell of cells) {
      if (
        !Number.isFinite(cell.x) ||
        !Number.isFinite(cell.y) ||
        !Number.isFinite(cell.width) ||
        !Number.isFinite(cell.height) ||
        cell.width <= 0 ||
        cell.height <= 0
      ) {
        continue;
      }

      const glowHeight = Math.max(8, cell.height * 3.2);
      const glow = context.createLinearGradient(0, cell.y - glowHeight, 0, cell.y + glowHeight);
      glow.addColorStop(0, "rgba(0, 0, 0, 0)");
      glow.addColorStop(0.5, colorStop(cell.intensity, 0.36));
      glow.addColorStop(1, "rgba(0, 0, 0, 0)");
      context.fillStyle = glow;
      context.fillRect(cell.x, cell.y - glowHeight / 2, cell.width, glowHeight);

      context.fillStyle = colorStop(cell.intensity, 1);
      context.fillRect(cell.x, cell.y - cell.height / 2, cell.width, cell.height);
    }

    context.globalCompositeOperation = "source-over";
    const shade = context.createLinearGradient(0, 0, width, 0);
    shade.addColorStop(0, "rgba(255, 255, 255, .035)");
    shade.addColorStop(0.58, "rgba(255, 255, 255, 0)");
    shade.addColorStop(1, "rgba(0, 0, 0, .34)");
    context.fillStyle = shade;
    context.fillRect(0, 0, width, height);
  }, [cells, height, width]);

  return <canvas ref={canvasRef} className="heatmap-canvas" aria-hidden="true" />;
}
