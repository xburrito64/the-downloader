<script>
  // One download as a row: cover, names, what is happening, and its buttons. Used by Queue and Library.
  import Cover from "./Cover.svelte";
  import { api } from "./api.js";
  import { attempt, notify, progress, putJob } from "./state.svelte.js";
  import { speed } from "./format.js";

  let { job, onforget = null } = $props();

  const live = $derived(progress[job.id]);
  const fraction = $derived(job.status === "done" ? 1 : (live?.fraction ?? 0));
  const stages = { downloading: "Downloading", converting: "Converting", tagging: "Adding tags" };

  const line = $derived.by(() => {
    switch (job.status) {
      case "queued": return "Waiting";
      case "paused": return "Paused";
      case "done": return "Saved";
      case "cancelled": return "Cancelled";
      case "skipped": return "Skipped";
      case "failed": return job.error || "Failed";
      default: {
        if (!live) return "Starting";
        const rate = speed(live.speed);
        return `${stages[live.stage] ?? "Working"} ${Math.round(live.fraction * 100)}%${rate ? `, ${rate}` : ""}`;
      }
    }
  });

  async function act(action) {
    const updated = await attempt(() => api.job(job.id, action));
    if (updated && action !== "reveal") putJob(updated);
  }

  async function retry() {
    await act("retry");
    notify("Trying again. It is back in the queue.");
  }
</script>

<div class="row" class:failed={job.status === "failed"} class:done={job.status === "done"}>
  <div class="art"><Cover url={job.cover_url} label={job.title} /></div>
  <div class="text">
    <h4 title={job.title}>{job.title}</h4>
    <p class="who">{[job.artist, job.group].filter(Boolean).join(" · ") || (job.provider === "youtube" ? "YouTube" : "Spotify")}</p>
    <p class="state" title={job.status === "failed" ? line : null}>{line}</p>
    {#if job.status === "running" || job.status === "paused"}
      <div class="bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.round(fraction * 100)}>
        <i style:transform="scaleX({fraction})"></i>
      </div>
    {/if}
  </div>
  <div class="actions">
    {#if job.status === "running" || job.status === "queued"}
      <button class="key" onclick={() => act("pause")}>Pause</button>
      <button class="key" onclick={() => act("cancel")}>Cancel</button>
    {:else if job.status === "paused"}
      <button class="key" onclick={() => act("resume")}>Resume</button>
      <button class="key" onclick={() => act("cancel")}>Cancel</button>
    {:else if job.status === "failed"}
      <button class="key" onclick={retry}>Try again</button>
    {:else if job.status === "done"}
      <button class="key" onclick={() => act("reveal")}>Show file</button>
    {/if}
    {#if onforget}
      <button class="key quiet" onclick={() => onforget(job)} title="Remove from this list. The file stays.">Remove</button>
    {/if}
  </div>
</div>

<style>
  .row {
    display: grid; grid-template-columns: 64px minmax(0, 1fr) auto; gap: 14px; align-items: center;
    background: var(--raised); border-radius: var(--r-m); padding: 8px 14px 8px 8px; height: 100%;
    box-shadow: 0 4px 0 var(--edge);
  }
  .text { min-width: 0; display: grid; gap: 1px; }
  h4 { margin: 0; font: 800 15px/1.25 var(--font-body); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  p { font-size: 13px; color: var(--ink-soft); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .state { font-weight: 700; }
  .done .state { color: var(--good); }
  .failed .state { color: var(--rose); }
  .bar { height: 8px; border-radius: 4px; background: var(--edge); overflow: hidden; margin-top: 4px; }
  .bar i { display: block; height: 100%; background: var(--accent); transform-origin: left; transition: transform 300ms linear; }
  .actions { display: flex; gap: 8px; }
  .quiet { background: var(--panel); color: var(--ink-soft); }
</style>
