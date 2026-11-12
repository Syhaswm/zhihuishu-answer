export const COPY_HOTKEY = "CommandOrControl+Shift+KeyC";
export const PREV_QUESTION_HOTKEY = "CommandOrControl+Shift+ArrowUp";
export const NEXT_QUESTION_HOTKEY = "CommandOrControl+Shift+ArrowDown";
export const PREV_PART_HOTKEY = "CommandOrControl+Shift+ArrowLeft";
export const NEXT_PART_HOTKEY = "CommandOrControl+Shift+ArrowRight";

const ANSWER_HOTKEYS = [
  COPY_HOTKEY,
  PREV_QUESTION_HOTKEY,
  NEXT_QUESTION_HOTKEY,
  PREV_PART_HOTKEY,
  NEXT_PART_HOTKEY,
];

async function shortcutApi() {
  const { isTauri } = await import("@tauri-apps/api/core");
  if (!isTauri()) return null;
  return import("@tauri-apps/plugin-global-shortcut");
}

export async function registerAnswerHotkeys(handlers) {
  const api = await shortcutApi();
  if (!api) return [];
  const pairs = [
    [COPY_HOTKEY, handlers.copy],
    [PREV_QUESTION_HOTKEY, handlers.prevQuestion],
    [NEXT_QUESTION_HOTKEY, handlers.nextQuestion],
    [PREV_PART_HOTKEY, handlers.prevPart],
    [NEXT_PART_HOTKEY, handlers.nextPart],
  ];
  const registered = [];
  for (const [accelerator, handler] of pairs) {
    if (typeof handler !== "function") continue;
    try {
      await api.register(accelerator, (event) => {
        if (event.state === "Pressed") handler();
      });
      registered.push(accelerator);
    } catch {
      /* 某个快捷键被系统占用时，其余仍可用 */
    }
  }
  return registered;
}

export async function unregisterAnswerHotkeys() {
  const api = await shortcutApi();
  if (!api) return;
  try {
    await api.unregister(ANSWER_HOTKEYS);
  } catch {
    for (const accelerator of ANSWER_HOTKEYS) {
      try {
        await api.unregister(accelerator);
      } catch {
        /* 未注册过 */
      }
    }
  }
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
