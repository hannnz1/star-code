// Ordered Bayer dithering, generated once. No remote image or animated canvas.
const bayer = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]];
const pixels: string[] = [];
for (let y = 0; y < 64; y++) {
  for (let x = 0; x < 96; x++) {
    const dx = (x - 49) / 29, dy = (y - 32) / 29;
    const radius = dx * dx + dy * dy;
    let light = 0;
    if (radius < 1) light = Math.max(0.03, Math.min(1, .24 + .68 * Math.sqrt(1 - radius) - .32 * dx - .28 * dy));
    const ring = Math.abs(Math.sqrt(((x - 49) / 44) ** 2 + ((y - 32 + (x - 49) * .27) / 14) ** 2) - 1);
    if (ring < .025 && (dy > .08 || radius > 1)) light = .78;
    if (light > (bayer[y % 4][x % 4] + .5) / 16) pixels.push(`M${x * 4} ${y * 4}h4v4h-4z`);
  }
}
const pattern = pixels.join('');

export function DitherArtwork({className = ''}: {className?: string}) {
  return <svg className={`commerce-dither ${className}`} viewBox="0 0 384 256" aria-hidden="true" focusable="false">
    <path d={pattern} fill="currentColor" shapeRendering="crispEdges"/>
  </svg>;
}
