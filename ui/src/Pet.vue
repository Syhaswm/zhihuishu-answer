<script setup>
import { onMounted, onUnmounted, ref } from "vue";
import { petSnapRect } from "./pet-snap";
import "./pet.css";

const side = ref("right");
const menuOpen = ref(false);
let stopMove = () => {};
let snapTimer = null;

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
  stopMove();
});
</script>

<template>
  <div class="pet" :class="`pet--${side}`" @contextmenu.prevent="menuOpen = true" @click.self="menuOpen = false">
    <div class="grip" data-tauri-drag-region>
      <i class="hand" />
      <i class="hand" />
    </div>
    <button class="body" type="button" title="打开智慧树答题" @click="openApp">
      <span class="face">
        <i class="leaf" />
        <span class="eyes"><i /><i /></span>
        <i class="mouth" />
      </span>
    </button>
    <div v-if="menuOpen" class="menu">
      <button type="button" @click="openApp">打开</button>
      <button type="button" @click="quitApp">退出</button>
    </div>
  </div>
</template>
