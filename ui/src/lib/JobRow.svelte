<script>
  // One download as a row: cover, names, what is happening, and its buttons. Used by Queue and Library.
  import Cover from "./Cover.svelte";
  import { api } from "./api.js";
  import { app, attempt, finishedAt, notify, progress } from "./state.svelte.js";
  import { speed } from "./format.js";

  let { job, onforget = null } = $props();

  const live = $derived(progress[job.id]);
  const fraction = $derived(job.status === "done" ? 1 : (live?.fraction ?? 0));
  // The finish moment, part 3: finished rows in the Queue carry a wooden "Got it" plank.
  // It thumps down only right after the download finished; later (scrolling back, switching screens) it just sits there.
  const fresh = $derived(job.status === "done" && Date.now() - (finishedAt.get(job.id) ?? 0) < 1500);
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
        if (!live || live.stage === "waiting") return "Starting";
        const rate = speed(live.speed);
        return `${stages[live.stage] ?? "Working"} ${Math.round(live.fraction * 100)}%${rate ? `, ${rate}` : ""}`;
      }
    }
  });

  // The answer to a button press is not used to update the row: the engine announces every
  // change as a live update, and an answer can arrive after a newer update and undo it.
  function act(action) {
    return attempt(() => api.job(job.id, action));
  }

  async function retry() {
    if (await act("retry")) notify("Trying again. It is back in the queue.");
  }
</script>

<div class="row" class:thud={fresh && !onforget} class:wide={job.provider === "youtube"} class:failed={job.status === "failed"} class:done={job.status === "done"}>
  <div class="art"><Cover url={job.cover_url} label={job.title} wide={job.provider === "youtube"} /></div>
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
      {#if !onforget}<span class="stamp" class:fresh>Got it<i></i><i></i><i></i><i></i></span>{/if}
      <button class="key" onclick={() => act("reveal")}>Show file</button>
    {/if}
    {#if job.provider === "spotify" && ["failed", "cancelled", "done"].includes(job.status)}
      <button class="key" class:quiet={job.status === "done"} onclick={() => (app.matchFor = job)}
        title="Choose the YouTube Music recording yourself">Other match</button>
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
  .row.wide { grid-template-columns: 114px minmax(0, 1fr) auto; }
  .text { min-width: 0; display: grid; gap: 1px; }
  h4 { margin: 0; font: 800 15px/1.25 var(--font-body); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  p { font-size: 13px; color: var(--ink-soft); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .state { font-weight: 700; }
  .done .state { color: var(--good); }
  .failed .state { color: var(--rose); }
  .bar { height: 8px; border-radius: 4px; background: var(--edge); overflow: hidden; margin-top: 4px; }
  .bar i { display: block; height: 100%; background: var(--accent); transform-origin: left; transition: transform 300ms linear; }
  .actions { display: flex; gap: 8px; align-items: center; }
  .stamp {
    position: relative; margin-right: 10px; padding: 3px 11px 5px; font: 400 22px/1 var(--font-display); color: var(--ink); white-space: nowrap;
    background: var(--wood); box-shadow: 0 0 0 3px var(--wood-dark), inset 0 3px 0 var(--wood-lit); transform: rotate(-7deg);
  }
  .stamp.fresh { animation: stamp 260ms steps(4) both; }
  @keyframes stamp { from { transform: scale(2.2) rotate(-16deg); opacity: 0; } }
  .stamp i { position: absolute; width: 6px; height: 6px; background: var(--accent); opacity: 0; }
  .stamp.fresh i { animation: spark 420ms steps(4) 230ms; }
  .stamp i:nth-child(1) { left: -3px; top: -3px; --dx: -15px; --dy: -12px; }
  .stamp i:nth-child(2) { right: -3px; top: -3px; --dx: 15px; --dy: -12px; }
  .stamp i:nth-child(3) { left: -3px; bottom: -3px; --dx: -15px; --dy: 12px; }
  .stamp i:nth-child(4) { right: -3px; bottom: -3px; --dx: 15px; --dy: 12px; }
  @keyframes spark { from { opacity: 1; transform: none; } to { opacity: 0; transform: translate(var(--dx), var(--dy)); } }
  .row.thud { animation: thud 200ms steps(3) 220ms; }
  @keyframes thud { 50% { transform: translateY(3px); } }
  .quiet { background: var(--panel); color: var(--ink-soft); }
</style>
