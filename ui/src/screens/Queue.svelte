<script>
  import { api } from "../lib/api.js";
  import { activeCount, app, attempt, clearAll, clearFinished, failedCount, notify } from "../lib/state.svelte.js";
  import { plural } from "../lib/format.js";
  import JobRow from "../lib/JobRow.svelte";
  import VirtualGrid from "../lib/VirtualGrid.svelte";

  const waiting = $derived(activeCount());
  const failed = $derived(failedCount());
  const saved = $derived(app.jobs.filter((job) => job.status === "done").length);
  const clearable = $derived(app.jobs.length - waiting - failed);
  const anyPaused = $derived(app.jobs.some((job) => job.status === "paused"));
  const anyMoving = $derived(app.jobs.some((job) => job.status === "running" || job.status === "queued"));

  // "Didn't download" shows only the failed ones, so they are easy to find in a long playlist.
  let onlyFailed = $state(false);
  $effect(() => { if (!failed) onlyFailed = false; });
  const shown = $derived(onlyFailed ? app.jobs.filter((job) => job.status === "failed") : app.jobs);

  // Clear all asks once more when it would also stop downloads that are not finished.
  let confirming = $state(false);
  let confirmTimer = 0;
  function clearEverything() {
    if (waiting && !confirming) {
      confirming = true;
      clearTimeout(confirmTimer);
      confirmTimer = setTimeout(() => (confirming = false), 4000);
      return;
    }
    confirming = false;
    clearAll();
  }

  let retrying = $state(false);
  async function retryAll() {
    retrying = true;
    const ids = app.jobs.filter((job) => job.status === "failed").map((job) => job.id);
    let started = 0;
    for (const id of ids) if (await attempt(() => api.job(id, "retry"))) started++;
    retrying = false;
    if (started) notify(`Trying ${plural(started, "download")} again.`);
  }
</script>

<div class="screen" class:open={!app.jobs.length}>
  <div class="head">
    <h1>Queue</h1>
    <span class="sub">
      {#if waiting}{plural(waiting, "download")} to go{:else if app.jobs.length}All done{:else}Nothing waiting{/if}{#if saved}, {saved} saved{/if}
    </span>
    {#if anyMoving}<button class="key" onclick={() => attempt(api.pauseAll)}>Pause all</button>{/if}
    {#if anyPaused}<button class="key" onclick={() => attempt(api.resumeAll)}>Resume all</button>{/if}
    {#if clearable}<button class="key" onclick={clearFinished} title="Takes away what went well. Downloads that failed stay.">Clear finished</button>{/if}
    {#if app.jobs.length}
      <button class="key" class:danger={confirming} onclick={clearEverything}
        title="Empties the whole queue, failed and unfinished downloads included. Saved files and the Library stay.">
        {confirming ? `Also stop ${waiting}? Click again` : "Clear all"}
      </button>
    {/if}
  </div>

  {#if failed}
    <div class="problems" role="status">
      <b>{failed === 1 ? "1 didn't download" : `${failed} didn't download`}</b>
      <span class="seg" role="group" aria-label="Which downloads to show">
        <button aria-pressed={!onlyFailed} onclick={() => (onlyFailed = false)}>All</button>
        <button aria-pressed={onlyFailed} onclick={() => (onlyFailed = true)}>Only these</button>
      </span>
      <button class="key" onclick={retryAll} disabled={retrying}>{retrying ? "Starting" : "Try all again"}</button>
    </div>
  {/if}

  {#if shown.length}
    <VirtualGrid items={shown} itemHeight={84} gap={10}>
      {#snippet cell(job)}
        <JobRow {job} />
      {/snippet}
    </VirtualGrid>
  {:else}
    <p class="empty">
      <strong>The queue is empty.</strong>
      Downloads show up here while they run. Finished ones are kept in the Library.
    </p>
  {/if}
</div>

<style>
  .problems { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; margin-right: 10px; padding: 8px 10px 8px 16px;
    background: var(--edge); border-radius: var(--r-m); box-shadow: inset 4px 0 0 var(--rose); }
  .problems b { color: var(--rose); font: 400 24px/1 var(--font-display); margin-right: auto; }
  .problems .key { background: var(--raised); }
  .danger { background: var(--rose) !important; color: var(--edge); }
</style>
