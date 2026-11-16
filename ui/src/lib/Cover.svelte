<script>
  import { coverSrc } from "./api.js";
  import { tint } from "./format.js";

  let { url = "", label = "" } = $props();
  let failed = $state(false);
  // A new item in the same spot (lists reuse their rows) gets a fresh try.
  $effect(() => { url; failed = false; });
</script>

<div class="cover" style:background={tint(label)}>
  {#if url && !failed}
    <img src={coverSrc(url)} alt="" loading="lazy" decoding="async" draggable="false" onerror={() => (failed = true)}>
  {/if}
</div>

<style>
  .cover { aspect-ratio: 1; border-radius: var(--r-s); overflow: hidden; position: relative; }
  img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; display: block; }
</style>
