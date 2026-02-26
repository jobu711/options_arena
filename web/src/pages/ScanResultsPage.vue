<script setup lang="ts">
import { useRoute } from 'vue-router'

const route = useRoute()
const scanId = route.params.id
</script>

<template>
  <div class="page">
    <h1>Scan Results #{{ scanId }}</h1>
    <p>Sortable and filterable ticker score table.</p>
  </div>
</template>
