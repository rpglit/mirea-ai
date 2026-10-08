<script setup>
import { ref } from "vue";
import { SMOKE_TEXT, splitCsv, toInt, toast } from "../store";

const emit = defineEmits(["run"]);

const format = ref("text");
const text = ref(SMOKE_TEXT);
const jsonText = ref("");
const sessionName = ref("");

// form channel
const formPlaces = ref("");
const formTransitions = ref("");
const formMarking = ref("");
const formPriorities = ref("");
const formDelays = ref("");
const arcs = ref([
  { direction: "input", source: "", target: "", weight: "1" },
]);

function addArc() {
  arcs.value.push({ direction: "input", source: "", target: "", weight: "1" });
}

function removeArc(index) {
  arcs.value.splice(index, 1);
  if (!arcs.value.length) addArc();
}

function parseJsonBlock(value, label) {
  const raw = (value || "").trim();
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      toast(`${label}: ожидается JSON-объект`, true);
      return null;
    }
    return parsed;
  } catch (err) {
    toast(`Некорректный JSON в поле «${label}»: ${err.message}`, true);
    return null;
  }
}

function buildTextPayload() {
  return text.value;
}

function buildJsonPayload() {
  const raw = jsonText.value.trim();
  if (!raw) {
    toast("Введите JSON-описание", true);
    return null;
  }
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      toast("JSON-описание должно быть объектом", true);
      return null;
    }
    return parsed;
  } catch (err) {
    toast("Некорректный JSON: " + err.message, true);
    return null;
  }
}

function buildFormPayload() {
  const places = splitCsv(formPlaces.value);
  const transitions = splitCsv(formTransitions.value);
  if (!places.length) {
    toast("Укажите хотя бы одну позицию", true);
    return null;
  }
  if (!transitions.length) {
    toast("Укажите хотя бы один переход", true);
    return null;
  }
  const arcList = [];
  arcs.value.forEach((arc, i) => {
    const source = (arc.source || "").trim();
    const target = (arc.target || "").trim();
    if (!source || !target) return;
    let weight;
    if (arc.direction === "inhibitor") {
      const rawWeight = (arc.weight || "").trim();
      if (rawWeight !== "" && toInt(rawWeight) !== 1) {
        toast(`Дуга ${i + 1}: вес ингибиторной дуги должен быть 1`, true);
        return null;
      }
      weight = 1;
    } else {
      const w = toInt(arc.weight);
      if (w === null || w < 1) {
        toast(`Дуга ${i + 1} (${source} → ${target}): вес должен быть целым ≥ 1`, true);
        return null;
      }
      weight = w;
    }
    arcList.push({
      source,
      target,
      weight,
      direction: arc.direction || "input",
    });
  });
  const markingParts = splitCsv(formMarking.value);
  if (markingParts.length !== places.length) {
    toast(`Начальная маркировка должна содержать ${places.length} значений`, true);
    return null;
  }
  const initialMarking = {};
  for (let i = 0; i < places.length; i += 1) {
    const value = toInt(markingParts[i]);
    if (value === null || value < 0) {
      toast("Значения начальной маркировки должны быть целыми числами ≥ 0", true);
      return null;
    }
    initialMarking[places[i]] = value;
  }
  const priorities = parseJsonBlock(formPriorities.value, "приоритеты");
  if (priorities === null) return null;
  const delays = parseJsonBlock(formDelays.value, "задержки");
  if (delays === null) return null;
  return {
    places,
    transitions,
    arcs: arcList,
    initial_marking: initialMarking,
    ...(Object.keys(priorities).length ? { priorities } : {}),
    ...(Object.keys(delays).length ? { delays } : {}),
  };
}

function runCurrent() {
  let payload;
  if (format.value === "text") payload = buildTextPayload();
  else if (format.value === "json") payload = buildJsonPayload();
  else payload = buildFormPayload();
  if (payload === null) return;
  const name = sessionName.value.trim() || null;
  sessionName.value = "";
  emit("run", format.value, payload, name);
}
</script>

<template>
  <div class="intake">
    <label for="session-name">Имя сессии (необязательно)</label>
    <input
      id="session-name"
      v-model="sessionName"
      class="form-field"
      style="max-width: 380px"
      placeholder="Например: «Эталонная сеть»"
    />

    <nav class="tabs" id="input-tabs">
      <button
        type="button"
        id="tab-text"
        class="tab"
        :class="{ active: format === 'text' }"
        @click="format = 'text'"
      >
        Текстовый ввод
      </button>
      <button
        type="button"
        id="tab-json"
        class="tab"
        :class="{ active: format === 'json' }"
        @click="format = 'json'"
      >
        JSON
      </button>
      <button
        type="button"
        id="tab-form"
        class="tab"
        :class="{ active: format === 'form' }"
        @click="format = 'form'"
      >
        Форма
      </button>
    </nav>

    <section id="panel-text" v-show="format === 'text'">
      <label for="input-text">Описание сети в математической нотации</label>
      <textarea id="input-text" v-model="text" rows="10" spellcheck="false"></textarea>
      <button type="button" id="btn-run-text" class="primary" @click="runCurrent">
        Проанализировать
      </button>
    </section>

    <section id="panel-json" v-show="format === 'json'">
      <label for="input-json">
        JSON-описание (places, transitions, inputs, outputs, initial_marking;
        опц. inhibitors, priorities, delays)
      </label>
      <textarea
        id="input-json"
        v-model="jsonText"
        rows="10"
        spellcheck="false"
        placeholder='{"places": ["p1"], "transitions": ["t1"], "inputs": {...}, "outputs": {...}, "initial_marking": {...}}'
      ></textarea>
      <button type="button" id="btn-run-json" class="primary" @click="runCurrent">
        Проанализировать
      </button>
    </section>

    <section id="panel-form" v-show="format === 'form'">
      <div class="form-field">
        <label for="form-places">Позиции (через запятую)</label>
        <input id="form-places" v-model="formPlaces" placeholder="p1, p2, p3" />
      </div>
      <div class="form-field">
        <label for="form-transitions">Переходы (через запятую)</label>
        <input id="form-transitions" v-model="formTransitions" placeholder="t1, t2" />
      </div>
      <label>Дуги</label>
      <div id="arcs-list">
        <div v-for="(arc, i) in arcs" :key="i" class="arc-row">
          <select v-model="arc.direction" class="arc-direction" title="Вид дуги">
            <option value="input">вход (позиция → переход)</option>
            <option value="output">выход (переход → позиция)</option>
            <option value="inhibitor">ингибитор (⊣, позиция → переход)</option>
          </select>
          <input v-model="arc.source" class="arc-source" placeholder="p1" />
          <input v-model="arc.target" class="arc-target" placeholder="t1" />
          <input
            v-model="arc.weight"
            class="arc-weight"
            type="number"
            min="1"
            :disabled="arc.direction === 'inhibitor'"
            title="Кратность дуги (≥ 1)"
          />
          <button type="button" class="arc-remove" title="Удалить дугу" @click="removeArc(i)">
            ✕
          </button>
        </div>
      </div>
      <button type="button" id="btn-add-arc" @click="addArc">+ Добавить дугу</button>
      <div class="form-field">
        <label for="form-marking">
          Начальная маркировка (через запятую, в порядке позиций)
        </label>
        <input id="form-marking" v-model="formMarking" placeholder="7, 4, 2, 5, 4, 3" />
      </div>
      <div class="form-field">
        <label for="form-priorities">Приоритеты, JSON (необязательно)</label>
        <input
          id="form-priorities"
          v-model="formPriorities"
          placeholder='{"t1": 1, "t2": 0}'
        />
      </div>
      <div class="form-field">
        <label for="form-delays">Задержки τ, JSON (необязательно)</label>
        <input
          id="form-delays"
          v-model="formDelays"
          placeholder='{"t1": {"p2": 4}}'
        />
      </div>
      <button type="button" id="btn-run-form" class="primary" @click="runCurrent">
        Проанализировать
      </button>
    </section>
  </div>
</template>
