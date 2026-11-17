<script>
  import { api } from "../lib/api.js";
  import { activeCount, app, attempt, clearFinished } from "../lib/state.svelte.js";
  import { plural } from "../lib/format.js";
  import JobRow from "../lib/JobRow.svelte";
  import VirtualGrid from "../lib/VirtualGrid.svelte";

  const waiting = $derived(activeCount());
  const finished = $derived(app.jobs.length - waiting);
  const anyPaused = $derived(app.jobs.some((job) => job.status === "paused"));
  const anyMoving = $derived(app.jobs.some((job) => job.status === "running" || job.status === "queued"));
</script>

<div class="screen" class:open={!app.jobs.length}>
  <div class="head">
    <h1>Queue</h1>
    <span class="sub">{waiting ? `${plural(waiting, "download")} to go` : "Nothing waiting"}</span>
    {#if anyMoving}<button class="key" onclick={() => attempt(api.pauseAll)}>Pause all</button>{/if}
    {#if anyPaused}<button class="key" onclick={() => attempt(api.resumeAll)}>Resume all</button>{/if}
    {#if finished}<button class="key" onclick={clearFinished}>Clear finished</button>{/if}
  </div>

  {#if app.jobs.length}
    <VirtualGrid items={app.jobs} itemHeight={84} gap={10}>
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
