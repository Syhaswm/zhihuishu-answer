import { createApp } from "vue";

const pet = window.__ZHS_PET__ === true || new URLSearchParams(window.location.search).get("pet") === "1";

async function boot() {
  if (pet) {
    const { default: Pet } = await import("./Pet.vue");
    createApp(Pet).mount("#app");
    return;
  }
  await import("./style.css");
  const { default: App } = await import("./App.vue");
  createApp(App).mount("#app");
}

boot();
