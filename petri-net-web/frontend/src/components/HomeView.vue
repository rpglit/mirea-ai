<script setup>
import TaskPicker from "./TaskPicker.vue";
import SolverView from "./SolverView.vue";
import { store } from "../store";

function select(task) {
  store.task = task;
  store.solverReport = null;
}
</script>

<template>
  <section class="home">
    <TaskPicker @select="select" />
    <SolverView v-if="store.task" :task="store.task" />
  </section>
</template>
