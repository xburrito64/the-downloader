<script>
  import { coverSrc } from "./api.js";
  import { tint } from "./format.js";

  // wide: the 16:9 shape of a video picture. Otherwise square, like an album cover.
  let { url = "", label = "", wide = false } = $props();
  let failed = $state(false);
  // A new item in the same spot (lists reuse their rows) gets a fresh try.
  $effect(() => { url; failed = false; });
</script>

<div class="cover" class:wide style:background={tint(label)}>
  {#if url && !failed}
    <img src={coverSrc(url, wide)} alt="" loading="lazy" decoding="async" draggable="false" onerror={() => (failed = true)}>
  {/if}
</div>

<style>
  .cover { aspect-ratio: 1; border-radius: var(--r-s); overflow: hidden; position: relative; }
  .wide { aspect-ratio: 16 / 9; }
  img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; display: block; }
</style>
