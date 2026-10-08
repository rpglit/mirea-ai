import { createApp } from "vue";
import App from "./App.vue";
import "./style.css";

window.Registry = { net: null, graph: null, automaton: null };

createApp(App).mount("#app");
