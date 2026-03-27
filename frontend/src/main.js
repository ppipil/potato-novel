import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import App from "./App.vue";
import { routes } from "./routes";
import "./styles.css";

const FRONTEND_DEBUG_KEY = "potato-novel-debug-frontend";

const router = createRouter({
  history: createWebHistory(),
  routes
});

function isFrontendDebugEnabled() {
  try {
    return localStorage.getItem(FRONTEND_DEBUG_KEY) === "1";
  } catch {
    return false;
  }
}

router.beforeEach((to, from, next) => {
  if (isFrontendDebugEnabled()) {
    console.log("[potato-frontend] route", {
      from: from.fullPath,
      to: to.fullPath
    });
  }
  next();
});

createApp(App).use(router).mount("#app");
