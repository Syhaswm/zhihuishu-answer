<script setup>
import { onMounted, onUnmounted, ref } from "vue";
import { petSnapRect } from "./pet-snap";
import "./pet.css";

const side = ref("right");
const menuOpen = ref(false);
const celebrate = ref(false);
let stopMove = () => {};
let snapTimer = null;
let celebrateTimer = null;

async function windowApi() {
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  return getCurrentWindow();
}

async function invoke(cmd) {
  const { invoke: call } = await import("@tauri-apps/api/core");
  return call(cmd);
}

async function openApp() {
  menuOpen.value = false;
  try {
    await invoke("show_main");
    celebrate.value = true;
    clearTimeout(celebrateTimer);
    celebrateTimer = setTimeout(() => {
      celebrate.value = false;
    }, 520);
  } catch {
    /* 主窗口还没起来时忽略 */
  }
}

async function quitApp() {
  try {
    await invoke("quit_app");
  } catch {
    window.close();
  }
}

async function snapToEdge() {
  const win = await windowApi();
  const pos = await win.outerPosition();
  const size = await win.outerSize();
  const monitor = await win.currentMonitor();
  const area = monitor?.workArea;
  if (!area) return;
  const next = petSnapRect({
    pos: { x: pos.x, y: pos.y },
    size: { width: size.width, height: size.height },
    work: {
      x: area.position.x,
      y: area.position.y,
      width: area.size.width,
      height: area.size.height,
    },
  });
  side.value = next.side;
  if (Math.abs(next.x - pos.x) < 2 && Math.abs(next.y - pos.y) < 2) return;
  const { PhysicalPosition } = await import("@tauri-apps/api/dpi");
  await win.setPosition(new PhysicalPosition(Math.round(next.x), Math.round(next.y)));
}

onMounted(async () => {
  try {
    const win = await windowApi();
    stopMove = await win.onMoved(() => {
      clearTimeout(snapTimer);
      snapTimer = setTimeout(() => {
        snapToEdge().catch(() => {});
      }, 180);
    });
  } catch {
    /* 浏览器里预览时没有窗口接口 */
  }
});

onUnmounted(() => {
  clearTimeout(snapTimer);
  clearTimeout(celebrateTimer);
  stopMove();
});
</script>

<template>
  <div class="pet" :class="`pet--${side}`" @contextmenu.prevent="menuOpen = true" @click.self="menuOpen = false">
    <div class="grip" data-tauri-drag-region>
      <i class="hand" />
      <i class="hand" />
    </div>
    <button
      class="body"
      :class="{ 'body--celebrate': celebrate }"
      type="button"
      title="打开智慧树答题"
      @click="openApp"
    >
      <svg class="mascot" viewBox="0 0 80 88" width="76" height="84" aria-hidden="true">
        <defs>
          <radialGradient id="tree-face" cx="42%" cy="36%" r="58%">
            <stop offset="0%" stop-color="#5ecc82" />
            <stop offset="72%" stop-color="#36a85a" />
            <stop offset="100%" stop-color="#2a8f4a" />
          </radialGradient>
          <filter id="mascot-shadow" x="-20%" y="-10%" width="140%" height="130%">
            <feDropShadow dx="0" dy="3" stdDeviation="2.5" flood-color="#1a3d28" flood-opacity="0.28" />
          </filter>
        </defs>
        <g filter="url(#mascot-shadow)">
          <path
            class="mascot-leaf"
            d="M44 6 C52 2 62 8 58 18 C56 24 48 26 44 22 C40 18 38 10 44 6 Z"
            fill="#8ee06a"
          />
          <path
            class="mascot-leaf"
            d="M44 6 C52 2 62 8 58 18 C56 24 48 26 44 22 C40 18 38 10 44 6 Z"
            fill="#6fd04a"
            opacity="0.35"
            transform="translate(1,1)"
          />
          <ellipse cx="40" cy="48" rx="30" ry="32" fill="url(#tree-face)" />
          <ellipse cx="40" cy="52" rx="26" ry="24" fill="#2d9a52" opacity="0.12" />
          <ellipse class="mascot-eye" cx="28" cy="44" rx="7.5" ry="8.5" fill="#f8fff9" />
          <ellipse class="mascot-eye" cx="52" cy="44" rx="7.5" ry="8.5" fill="#f8fff9" />
          <circle class="mascot-pupil" cx="29.5" cy="45" r="3.6" fill="#1e3b28" />
          <circle class="mascot-pupil" cx="53.5" cy="45" r="3.6" fill="#1e3b28" />
          <circle cx="31" cy="43" r="1.2" fill="#fff" opacity="0.85" />
          <circle cx="55" cy="43" r="1.2" fill="#fff" opacity="0.85" />
          <ellipse cx="22" cy="54" rx="4" ry="2.6" fill="#ffb8a8" opacity="0.45" />
          <ellipse cx="58" cy="54" rx="4" ry="2.6" fill="#ffb8a8" opacity="0.45" />
          <path
            class="mascot-smile"
            d="M28 58 Q40 68 52 58"
            fill="none"
            stroke="#1e3b28"
            stroke-width="2.4"
            stroke-linecap="round"
          />
        </g>
      </svg>
    </button>
    <div v-if="menuOpen" class="menu">
      <button type="button" @click="openApp">打开</button>
      <button type="button" @click="quitApp">退出</button>
    </div>
  </div>
</template>