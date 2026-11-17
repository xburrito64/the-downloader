<script>
  import { api } from "../lib/api.js";
  import { app, attempt } from "../lib/state.svelte.js";
  import JobRow from "../lib/JobRow.svelte";
  import VirtualGrid from "../lib/VirtualGrid.svelte";

  const PAGE = 60;
  let search = $state("");
  let onlyFailed = $state(false);   // "Only these": only the ones that didn't download
  let failed = $state(0);           // how many in the whole Library didn't download
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
    const page = await attempt(() => api.history(search.trim(), reset ? 0 : entries.length, PAGE, onlyFailed));
    if (mine !== request) return;
    loading = false;
    loaded = true;
    if (!page) return;
    entries = reset ? page : [...entries, ...page];
    complete = page.length < PAGE;
  }

  // The notice counts the whole Library, not only the part loaded so far.
  async function countFailed() {
    const answer = await api.failedCount().catch(() => null);
    if (answer) failed = answer.count;
  }
  $effect(() => {
    app.historyVersion;
    countFailed();
  });
  $effect(() => { if (!failed) onlyFailed = false; });

  // Reload when the search text settles, and whenever a download finishes.
  let timer = 0;
  $effect(() => {
    search;
    onlyFailed;
    app.historyVersion;
    clearTimeout(timer);
    timer = setTimeout(() => load(true), 220);
    return () => clearTimeout(timer);
  });

  async function forget(job) {
    const done = await attempt(() => api.forget(job.id));
    if (done) entries = entries.filter((entry) => entry.id !== job.id);
    if (done && job.status === "failed") countFailed();
  }
</script>

<div class="screen" class:open={loaded && !entries.length}>
  <div class="head">
    <h1>Library</h1>
    <input class="well find" type="search" placeholder="Search title or artist" aria-label="Search the library" spellcheck="false" bind:value={search}>
  </div>

  {#if failed}
    <div class="problems" role="status">
      <b>{failed === 1 ? "1 didn't download" : `${failed} didn't download`}</b>
      <span class="seg" role="group" aria-label="Which downloads to show">
        <button aria-pressed={!onlyFailed} onclick={() => (onlyFailed = false)}>All</button>
        <button aria-pressed={onlyFailed} onclick={() => (onlyFailed = true)}>Only these</button>
      </span>
    </div>
  {/if}

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
        {onlyFailed ? `None of the ones that didn't download has "${search.trim()}" in its title or artist.`
          : `No download has "${search.trim()}" in its title or artist.`}
      {:else}
        <strong>Nothing here yet.</strong>
        Everything you download is listed here, newest first.
      {/if}
    </p>
  {/if}
</div>

<style>
  .find { width: 300px; }
  /* The same notice as in the Queue, for everything in the Library. */
  .problems { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; margin-right: 10px; padding: 8px 10px 8px 16px;
    background: var(--edge); border-radius: var(--r-m); box-shadow: inset 4px 0 0 var(--rose); }
  .problems b { color: var(--rose); font: 400 24px/1 var(--font-display); margin-right: auto; }
</style>
