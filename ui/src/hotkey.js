export const COPY_HOTKEY = "CommandOrControl+Shift+KeyC";

export async function registerCopyHotkey(handler) {
  const { isTauri } = await import("@tauri-apps/api/core");
  if (!isTauri()) return null;
  const { register } = await import("@tauri-apps/plugin-global-shortcut");
  await register(COPY_HOTKEY, (event) => {
    if (event.state === "Pressed") handler();
  });
  return COPY_HOTKEY;
}

export async function unregisterCopyHotkey() {
  const { isTauri } = await import("@tauri-apps/api/core");
  if (!isTauri()) return;
  const { unregister } = await import("@tauri-apps/plugin-global-shortcut");
  await unregister(COPY_HOTKEY);
}

export async function writeClipboard(text) {
  const value = String(text || "").trim();
  if (!value) return false;
  try {
    const { writeText } = await import("@tauri-apps/plugin-clipboard-manager");
    await writeText(value);
    return true;
  } catch {
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch {
      return false;
    }
  }
}
