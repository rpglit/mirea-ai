import { createApp } from "vue";
import App from "./App.vue";
import { store } from "./store";
import { applyTheme } from "./theme";
import "./theme/tokens.css";
import "./style.css";

window.Registry = { net: null, graph: null, automaton: null };

applyTheme(store.theme);

createApp(App).mount("#app");
