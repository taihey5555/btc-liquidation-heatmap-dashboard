export type HeatmapSourceBand = {
  price: number;
  start: number;
  end: number;
  intensity: number;
};

export type HeatmapCell = {
  x: number;
  y: number;
  width: number;
  height: number;
  intensity: number;
  drift: number;
};

export type TopZoneLine = {
  key: string;
  price: number;
  y: number;
  intensity: number;
  dominantSide?: string;
};

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function yForPrice(price: number, priceMin: number, priceMax: number, height: number) {
  const span = priceMax - priceMin;
  if (!Number.isFinite(span) || span <= 0) {
    return height / 2;
  }
  return height - ((price - priceMin) / span) * height;
}

function xForIndex(index: number, total: number, width: number) {
  return (index / Math.max(1, total - 1)) * width;
}

export function buildHeatmapCells({
  bands,
  priceMin,
  priceMax,
  width,
  height,
  indexTotal,
}: {
  bands: HeatmapSourceBand[];
  priceMin: number;
  priceMax: number;
  width: number;
  height: number;
  indexTotal: number;
}) {
  if (!Number.isFinite(priceMin) || !Number.isFinite(priceMax) || priceMax <= priceMin || width <= 0 || height <= 0) {
    return [];
  }

  return bands.flatMap((band, bandIndex) => {
    if (!Number.isFinite(band.price) || !Number.isFinite(band.intensity)) {
      return [];
    }

    const x = clamp(xForIndex(band.start, indexTotal, width), 0, width);
    const endX = clamp(xForIndex(band.end, indexTotal, width), 0, width);
    const cellWidth = Math.max(2, endX - x);
    const y = yForPrice(band.price, priceMin, priceMax, height);
    const intensity = clamp(band.intensity, 0.02, 1);
    const rowHeight = 1.15 + intensity * 2.2;
    const layerCount = intensity > 0.76 ? 11 : intensity > 0.54 ? 9 : 7;
    const segmentCount = Math.max(2, Math.min(9, Math.ceil(cellWidth / 118)));
    const segmentWidth = cellWidth / segmentCount;

    return Array.from({ length: layerCount * segmentCount }, (_, cellIndex) => {
      const layer = Math.floor(cellIndex / segmentCount);
      const segment = cellIndex % segmentCount;
      const offset = layer - (layerCount - 1) / 2;
      const stagger = ((bandIndex * 17 + layer * 11 + segment * 7) % 21) - 10;
      const segmentInset = segment === 0 ? 0 : (bandIndex + layer + segment) % 10;
      const segmentX = x + segment * segmentWidth + segmentInset;
      const fadeLeft = segment === 0 ? 0.9 : 1;
      const fadeRight = segment === segmentCount - 1 ? 0.82 : 1;
      const layerFade = 1 - Math.abs(offset) * 0.068;
      return {
        x: clamp(segmentX, 0, width),
        y: clamp(y + offset * (rowHeight + 1.35) + stagger * 0.08, 0, height),
        width: Math.max(10, segmentWidth - segmentInset - ((bandIndex + layer) % 12)),
        height: rowHeight,
        intensity: clamp(intensity * layerFade * fadeLeft * fadeRight, 0.02, 0.92),
        drift: stagger / 10,
      };
    });
  });
}

export function buildTopZoneLines({
  bands,
  priceMin,
  priceMax,
  width,
  height,
  limit = 5,
}: {
  bands: Array<HeatmapSourceBand & { dominantSide?: string; relativeIntensity?: number }>;
  priceMin: number;
  priceMax: number;
  width: number;
  height: number;
  limit?: number;
}): TopZoneLine[] {
  if (!Number.isFinite(priceMin) || !Number.isFinite(priceMax) || priceMax <= priceMin) {
    return [];
  }

  const minDistance = Math.max((priceMax - priceMin) * 0.018, 60);
  const selected: TopZoneLine[] = [];
  const candidates = [...bands]
    .filter((band) => band.price >= priceMin && band.price <= priceMax)
    .sort((a, b) => (b.relativeIntensity ?? b.intensity) - (a.relativeIntensity ?? a.intensity));

  for (const band of candidates) {
    if (selected.some((line) => Math.abs(line.price - band.price) < minDistance)) {
      continue;
    }
    selected.push({
      key: `${Math.round(band.price)}-${selected.length}`,
      price: band.price,
      y: clamp(yForPrice(band.price, priceMin, priceMax, height), 0, height),
      intensity: clamp(band.relativeIntensity ?? band.intensity, 0, 1),
      dominantSide: band.dominantSide,
    });
    if (selected.length >= limit) {
      break;
    }
  }

  return selected.map((line) => ({
    ...line,
    y: clamp(line.y, 10, height - 10),
    intensity: clamp(line.intensity, 0.18, 1),
  })).filter((line) => Number.isFinite(line.y) && width > 0);
}
