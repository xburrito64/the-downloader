<script>
  import { api } from "../lib/api.js";
  import { app, attempt } from "../lib/state.svelte.js";
  import JobRow from "../lib/JobRow.svelte";
  import VirtualGrid from "../lib/VirtualGrid.svelte";

  const PAGE = 60;
  let search = $state("");
  let entries = $state([]);
  let complete = $state(false);   // true once the last page has been loaded
  let loading = false;
  let loaded = $state(false);
  let request = 0;                // answers to an older search are thrown away

  async function load(reset) {
    if (loading && !reset) return;
    if (!reset && complete) return;
    const mine = ++request;
    loading = true;
    const page = await attempt(() => api.history(search.trim(), reset ? 0 : entries.length, PAGE));
    if (mine !== request) return;
    loading = false;
    loaded = true;
    if (!page) return;
    entries = reset ? page : [...entries, ...page];
    complete = page.length < PAGE;
  }

  // Reload when the search text settles, and whenever a download finishes.
  let timer = 0;
  $effect(() => {
    search;
    app.historyVersion;
    clearTimeout(timer);
    timer = setTimeout(() => load(true), 220);
    return () => clearTimeout(timer);
  });

  async function forget(job) {
    const done = await attempt(() => api.forget(job.id));
    if (done) entries = entries.filter((entry) => entry.id !== job.id);
  }
</script>

<div class="screen">
  <div class="head">
    <h1>Library</h1>
    <input class="well find" type="search" placeholder="Search title or artist" aria-label="Search the library" spellcheck="false" bind:value={search}>
  </div>

  {#if entries.length}
    <VirtualGrid items={entries} itemHeight={84} gap={10} onnearend={() => load(false)}>
      {#snippet cell(job)}
        <JobRow {job} onforget={forget} />
      {/snippet}
    </VirtualGrid>
  {:else if loaded}
    <p class="empty">
      {#if search.trim()}
        <strong>Nothing matches.</strong>
        No download has "{search.trim()}" in its title or artist.
      {:else}
        <strong>Nothing here yet.</strong>
        Everything you download is listed here, newest first.
      {/if}
    </p>
  {/if}
</div>

<style>
  .find { width: 300px; }
</style>
