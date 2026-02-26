<script setup lang="ts">
import { useRoute } from 'vue-router'

const route = useRoute()
const debateId = route.params.id
</script>

<template>
  <div class="page">
    <h1>Debate #{{ debateId }}</h1>
    <p>Full agent arguments, thesis, and export options.</p>
  </div>
</template>
