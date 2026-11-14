const DOCK_WIDTH_DEFAULT = 380;

export async function runningInTauri() {
  try {
    const { isTauri } = await import("@tauri-apps/api/core");
    return isTauri();
  } catch {
    return false;
  }
}

function normalizeOpacity(percent) {
  const n = Number(percent) || 100;
  if (n >= 100) return 100;
  if (n >= 95) return 95;
  if (n >= 90) return 90;
  return 85;
}

export async function applyWindowOpacity(percent = 100) {
  if (!(await runningInTauri())) return;
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("set_window_opacity", { opacity: normalizeOpacity(percent) });
}

export async function applyAlwaysOnTop(enabled = true) {
  if (!(await runningInTauri())) return;
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("set_always_on_top", { enabled: !!enabled });
}

const SNAP_LOGICAL = 28;
const LEAVE_LOGICAL = 56;
let suppressSnapUntil = 0;

export function edgeSnapDecision({ pos, size, work, scale, docked, dockSide }) {
  const factor = Number(scale) || 1;
  const snap = SNAP_LOGICAL * factor;
  const leave = LEAVE_LOGICAL * factor;
  const leftDist = pos.x - work.x;
  const rightDist = work.x + work.width - (pos.x + size.width);
  const side = String(dockSide || "off");
  if (docked) {
    if (side === "left" && leftDist > leave) return "off";
    if (side === "right" && rightDist > leave) return "off";
    return null;
  }
  const nearLeft = leftDist <= snap && leftDist >= -snap;
  const nearRight = rightDist <= snap && rightDist >= -snap;
  if (nearLeft && nearRight) return leftDist <= rightDist ? "left" : "right";
  if (nearLeft) return "left";
  if (nearRight) return "right";
  return null;
}

export async function applyDockLayout(
  side,
  width = DOCK_WIDTH_DEFAULT,
  alwaysOnTop = true,
  opacity = 100
) {
  if (!(await runningInTauri())) return;
  suppressSnapUntil = Date.now() + 900;
  const { invoke } = await import("@tauri-apps/api/core");
  const mode = String(side || "off").toLowerCase();
  if (mode === "off") {
    await invoke("dock_restore");
    await applyAlwaysOnTop(alwaysOnTop);
    return;
  }
  if (mode !== "left" && mode !== "right") {
    throw new Error("贴边位置只能是左侧或右侧");
  }
  const w = Math.min(560, Math.max(300, Number(width) || DOCK_WIDTH_DEFAULT));
  const o = normalizeOpacity(opacity);
  await invoke("dock_apply", { side: mode, width: w, alwaysOnTop: !!alwaysOnTop, opacity: o });
}

export async function startEdgeSnap(onSnap) {
  if (!(await runningInTauri())) return () => {};
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  const win = getCurrentWindow();
  let timer = null;
  const unlisten = await win.onMoved(() => {
    if (Date.now() < suppressSnapUntil) return;
    clearTimeout(timer);
    timer = setTimeout(async () => {
      if (Date.now() < suppressSnapUntil) return;
      try {
        if (await win.isMaximized()) return;
        const pos = await win.outerPosition();
        const size = await win.outerSize();
        const monitor = await win.currentMonitor();
        const area = monitor?.workArea;
        if (!area) return;
        const state = await onSnap.current();
        const decision = edgeSnapDecision({
          pos: { x: pos.x, y: pos.y },
          size: { width: size.width, height: size.height },
          work: { x: area.position.x, y: area.position.y, width: area.size.width, height: area.size.height },
          scale: monitor.scaleFactor,
          docked: !!state.docked,
          dockSide: state.dockSide,
        });
        if (!decision || decision === state.dockSide) return;
        await onSnap.apply(decision);
      } catch {
        /* 读不到显示器时不吸附 */
      }
    }, 220);
  });
  return () => {
    clearTimeout(timer);
    unlisten();
  };
}

export { DOCK_WIDTH_DEFAULT };
