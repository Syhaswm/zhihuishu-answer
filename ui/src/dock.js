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

export async function applyDockLayout(
  side,
  width = DOCK_WIDTH_DEFAULT,
  alwaysOnTop = true,
  opacity = 100
) {
  if (!(await runningInTauri())) return;
  const { invoke } = await import("@tauri-apps/api/core");
  const mode = String(side || "off").toLowerCase();
  if (mode === "off") {
    await invoke("dock_restore");
    return;
  }
  if (mode !== "left" && mode !== "right") {
    throw new Error("贴边位置只能是左侧或右侧");
  }
  const w = Math.min(560, Math.max(300, Number(width) || DOCK_WIDTH_DEFAULT));
  const o = normalizeOpacity(opacity);
  await invoke("dock_apply", { side: mode, width: w, alwaysOnTop: !!alwaysOnTop, opacity: o });
}

export { DOCK_WIDTH_DEFAULT };
