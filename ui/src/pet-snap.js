export function petSnapRect({ pos, size, work }) {
  const width = size.width;
  const height = size.height;
  const cx = pos.x + width / 2;
  const cy = pos.y + height / 2;
  const distances = [
    ["left", cx - work.x],
    ["right", work.x + work.width - cx],
    ["top", cy - work.y],
  ];
  distances.sort((a, b) => a[1] - b[1]);
  const edge = distances[0][0];
  const maxX = work.x + work.width - width;
  const maxY = work.y + work.height - height;
  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
  if (edge === "left") {
    return { x: work.x, y: clamp(pos.y, work.y, maxY), side: "left" };
  }
  if (edge === "right") {
    return { x: maxX, y: clamp(pos.y, work.y, maxY), side: "right" };
  }
  return { x: clamp(pos.x, work.x, maxX), y: work.y, side: "top" };
}
