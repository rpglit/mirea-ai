<script setup>
import { computed } from "vue";
import Formula from "./Formula.vue";
import AutomatonCanvas from "./AutomatonCanvas.vue";
import AnswerValue from "./AnswerValue.vue";
import { compactTuple, prettyFormula } from "../store";
import { faEnumToTex, markingToTex, matrixToTex, MATRIX_KEYS } from "../math/tex";

const props = defineProps({
  value: {},
  keyName: { type: String, default: "" },
  container: { type: Object, default: () => ({}) },
});

function isFaTable(v) {
  return v && typeof v === "object" && Array.isArray(v.cols) && Array.isArray(v.rows);
}

function isMealy(v) {
  return (
    v &&
    typeof v === "object" &&
    !Array.isArray(v) &&
    (v.enumeration !== undefined || v.table !== undefined || v.graph !== undefined)
  );
}

function isSubAnswer(v) {
  return (
    v &&
    typeof v === "object" &&
    !Array.isArray(v) &&
    !isFaTable(v) &&
    !isMealy(v) &&
    Object.keys(v).some((k) => k.endsWith("_tex"))
  );
}

function texSibling() {
  return props.container[props.keyName + "_tex"];
}

function cellText(val) {
  if (Array.isArray(val)) {
    if (val.length && val.every((x) => Array.isArray(x))) {
      return val.map((r) => compactTuple(r)).join("; ");
    }
    if (val.length && val.every((x) => x && typeof x === "object")) {
      return val.map((x) => JSON.stringify(x)).join("; ");
    }
    return compactTuple(val);
  }
  if (val !== null && typeof val === "object") return JSON.stringify(val);
  return prettyFormula(val);
}

function tupleText(value) {
  if (Array.isArray(value) && (value.length <= 12 || value.every((v) => typeof v === "number"))) {
    return `(${compactTuple(value)})`;
  }
  if (Array.isArray(value)) return value.map((v) => (Array.isArray(v) ? compactTuple(v) : v)).join("; ");
  return String(value);
}

const enumLines = computed(() => {
  const en = props.value && props.value.enumeration;
  if (!Array.isArray(en)) return [];
  return en.map((line) => ({ line: String(line), tex: faEnumToTex(line) }));
});

const isX0Like = computed(() => {
  const v = props.value;
  if (!v || typeof v !== "object" || Array.isArray(v)) return false;
  const tex = texSibling();
  if (!tex || typeof tex !== "object" || Array.isArray(tex)) return false;
  return Object.keys(v).every(
    (k) => typeof v[k] === "string" && typeof tex[k] === "string"
  );
});
</script>

<template>
  <span v-if="typeof value === 'string'">
    <Formula v-if="typeof texSibling() === 'string'" :tex="texSibling()" display />
    <pre v-else class="formula">{{ prettyFormula(value) }}</pre>
  </span>
  <span v-else-if="value === null">—</span>
  <span v-else-if="typeof value === 'number' || typeof value === 'boolean'">{{
    value === true ? "да" : value === false ? "нет" : value
  }}</span>
  <template v-else-if="Array.isArray(value)">
    <span v-if="!value.length">(пусто)</span>
    <Formula
      v-else-if="value.every((v) => typeof v === 'number' || v === null || v === undefined)"
      :tex="markingToTex(value)"
    />
    <template v-else-if="value.every((v) => Array.isArray(v))">
      <Formula v-if="MATRIX_KEYS.has(keyName)" :tex="matrixToTex(value)" display />
      <table
        v-else-if="
          value.length &&
          value.every(
            (row) => row.every((c) => typeof c === 'number' || c === null || c === undefined)
          )
        "
        class="data-table"
      >
        <tbody>
          <tr v-for="(row, i) in value" :key="i">
            <td><Formula :tex="markingToTex(row)" /></td>
          </tr>
        </tbody>
      </table>
      <table v-else class="data-table">
        <tbody>
          <tr v-for="(row, i) in value" :key="i">
            <td v-for="(cell, j) in row" :key="j">{{
              cell === null || cell === undefined ? "—" : typeof cell === "string" ? prettyFormula(cell) : cell
            }}</td>
          </tr>
        </tbody>
      </table>
    </template>
    <template
      v-else-if="
        value.every((v) => typeof v === 'string') &&
        Array.isArray(texSibling()) &&
        texSibling().length === value.length &&
        texSibling().every((x) => typeof x === 'string')
      "
    >
      <Formula v-for="(tex, i) in texSibling()" :key="i" :tex="tex" display />
    </template>
    <span v-else>{{ tupleText(value) }}</span>
  </template>
  <span v-else-if="isFaTable(value)">
    <table class="data-table">
      <thead>
        <tr>
          <th></th>
          <th v-for="col in value.cols" :key="col">{{ col }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(r, i) in value.rows" :key="i">
          <td>{{ r[0] }}</td>
          <td v-for="(cell, j) in r.slice(1)" :key="j">{{ cell }}</td>
        </tr>
      </tbody>
    </table>
  </span>
  <span v-else-if="isMealy(value)">
    <div v-for="(l, i) in enumLines" :key="i">
      <Formula v-if="l.tex" :tex="l.tex" display />
      <span v-else class="muted">{{ l.line }}</span>
    </div>
    <table v-if="value.table" class="data-table">
      <thead>
        <tr>
          <th></th>
          <th v-for="col in value.table.cols" :key="col">{{ col }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(r, i) in value.table.rows" :key="i">
          <td>{{ r[0] }}</td>
          <td v-for="(cell, j) in r.slice(1)" :key="j">{{ cell }}</td>
        </tr>
      </tbody>
    </table>
    <AutomatonCanvas v-if="value.graph" :graph="value.graph" :registry-key="keyName" />
  </span>
  <template v-else-if="isSubAnswer(value)">
    <template v-for="(subVal, subKey) in value" :key="subKey">
      <div v-if="!String(subKey).endsWith('_tex')" class="answer-block">
        <div class="answer-key">{{ subKey }}</div>
        <AnswerValue :value="subVal" :key-name="String(subKey)" :container="value" />
      </div>
    </template>
  </template>
  <template v-else>
    <table v-if="isX0Like" class="data-table">
      <tbody>
        <tr v-for="(v, k) in value" :key="k">
          <td style="font-weight: 600">{{ k }}</td>
          <td><Formula :tex="texSibling()[k]" display /></td>
        </tr>
      </tbody>
    </table>
    <table v-else class="data-table">
      <tbody>
        <tr v-for="(v, k) in value" :key="k">
          <td style="font-weight: 600">{{ k }}</td>
          <td>{{ cellText(v) }}</td>
        </tr>
      </tbody>
    </table>
  </template>
</template>
