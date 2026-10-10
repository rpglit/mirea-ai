<script setup>
import { computed } from "vue";
import { renderToString } from "katex";
import "katex/dist/katex.min.css";
import { toast } from "../store";

const props = defineProps({
  tex: { type: String, required: true },
  display: { type: Boolean, default: false },
  label: { type: String, default: "" },
});

const html = computed(() => {
  try {
    return {
      ok: true,
      katex: renderToString(props.tex, {
        displayMode: props.display,
        throwOnError: true,
      }),
    };
  } catch {
    return { ok: false, katex: "" };
  }
});

function execCommandCopy(text) {
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.setAttribute("readonly", "");
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  const ok = document.execCommand("copy");
  ta.remove();
  if (!ok) throw new Error("Не удалось скопировать TeX");
}

async function copyTex() {
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(props.tex);
    } else {
      execCommandCopy(props.tex);
    }
    toast("TeX скопирован");
  } catch (err) {
    toast(err instanceof Error && err.message ? err.message : "Не удалось скопировать TeX", true);
  }
}
</script>

<template>
  <span
    class="formula"
    :class="{ 'formula--display': display }"
    role="figure"
    :aria-label="label || tex"
    :title="tex"
    :data-tex="tex"
  >
    <span v-if="html.ok" class="formula__katex" aria-hidden="true" v-html="html.katex"></span>
    <code v-else class="formula__fallback">{{ label || tex }}</code>
    <button type="button" class="formula__copy" aria-label="Скопировать TeX" @click.stop="copyTex">
      ⧉
    </button>
  </span>
</template>
