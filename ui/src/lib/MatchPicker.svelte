<script>
  // Pick another YouTube Music recording for a Spotify song, when the automatic match was wrong or found nothing.
  import Cover from "./Cover.svelte";
  import { api } from "./api.js";
  import { app, attempt, notify } from "./state.svelte.js";
  import { duration } from "./format.js";

  let { job } = $props();
  let found = $state.raw(null);
  let problem = $state("");
  let busy = $state(false);
  let query = $state("");
  let searched = $state(""); // what the list shows: "" = the app's own suggestions
  let asked = 0; // only the newest answer counts when searches overlap

  function look(text) {
    const ask = ++asked;
    found = null;
    problem = "";
    searched = text;
    api.matches(job.id, text).then(
      (list) => ask === asked && (found = list),
      (error) => ask === asked && (problem = error.message),
    );
  }

  $effect(() => {
    look("");
    return () => asked++;
  });

  function submit(event) {
    event.preventDefault();
    look(query.trim());
  }

  const isLink = (text) => /youtu/i.test(text);

  function close() {
    app.matchFor = null;
  }

  async function use(candidate) {
    busy = true;
    const done = await attempt(() => api.rematch(job.id, candidate.video_id));
    busy = false;
    if (!done) return;
    notify(`Downloading "${job.title}" again from the recording you picked.`, "good");
    close();
  }

  function keys(event) {
    if (event.key === "Escape") close();
  }
</script>

<svelte:window onkeydown={keys} />

<div class="backdrop" role="presentation" onclick={(event) => event.target === event.currentTarget && close()}>
  <div class="panel" role="dialog" aria-modal="true" aria-labelledby="match-title">
    <div class="top">
      <div>
        <h2 id="match-title">Pick another match</h2>
        <p class="for"><b>{job.title}</b> by {job.artist || "unknown artist"}{job.status === "done" ? ". The file you have now is replaced." : "."}</p>
      </div>
      <button class="key" onclick={close}>Close</button>
    </div>

    <form class="search" onsubmit={submit}>
      <input class="well" type="search" bind:value={query} spellcheck="false" autocomplete="off"
        placeholder="Search YouTube Music, or paste a YouTube link" aria-label="Search YouTube Music or paste a link">
      <button class="key" type="submit">Search</button>
      {#if searched}<button class="key" type="button" onclick={() => { query = ""; look(""); }}>Suggestions</button>{/if}
    </form>

    {#if problem}
      <p class="problem">{problem}</p>
    {:else if !found}
      <p class="note">Searching YouTube Music</p>
    {:else if !found.length}
      <p class="note">{searched ? (isLink(searched) ? "That link is not a video YouTube Music can play." : "Nothing found for this search. Try other words, or paste a link from YouTube Music.")
        : "YouTube Music has nothing under this title and artist. Search above with other words, or paste a link."}</p>
    {:else}
      <ul>
        {#each found as candidate (candidate.video_id)}
          <li>
            <div class="art"><Cover url={`https://i.ytimg.com/vi/${candidate.video_id}/mqdefault.jpg`} label={candidate.title} wide /></div>
            <div class="text">
              <h4 title={candidate.title}>{candidate.title}</h4>
              <p>{candidate.artist || "Unknown artist"} · {duration(candidate.duration_seconds)} · {candidate.kind === "song" ? "Song" : "Video"}</p>
              <p class="fit" class:low={candidate.score < 0.6}>{Math.round(candidate.score * 100)}% fit{candidate.chosen ? " · picked before" : ""}</p>
            </div>
            <button class="key" onclick={() => api.listen(candidate.video_id).catch((error) => notify(error.message, "problem"))}>Listen</button>
            <button class="key use" onclick={() => use(candidate)} disabled={busy}>Use this</button>
          </li>
        {/each}
      </ul>
      <p class="note small">Fit is how well the title, artist and length agree with Spotify. Listen opens it in your browser. Not here? Search above, or find it on music.youtube.com and paste its link.</p>
    {/if}
  </div>
</div>

<style>
  .backdrop { position: fixed; inset: 0; z-index: 8; background: rgba(2, 15, 8, .7); display: grid; place-items: center; padding: 24px; }
  .panel {
    width: min(760px, 100%); max-height: 100%; display: flex; flex-direction: column; gap: 14px; padding: 20px 22px;
    background: var(--base); border-radius: var(--r-l); box-shadow: 0 0 0 3px var(--raised), 0 8px 0 var(--edge);
  }
  .search { display: flex; gap: 8px; }
  .search input { flex: 1; min-width: 0; padding: 10px 14px; border-radius: var(--r-m); font-size: 15px; }
  .top { display: flex; gap: 14px; align-items: flex-start; justify-content: space-between; }
  h2 { font: 400 34px/1 var(--font-display); }
  .for { color: var(--ink-soft); margin-top: 4px; }
  .for b { color: var(--ink); }
  ul { list-style: none; margin: 0; padding: 0 6px 6px 0; display: grid; gap: 10px; overflow-y: auto; min-height: 0; }
  li { display: grid; grid-template-columns: 100px minmax(0, 1fr) auto auto; gap: 12px; align-items: center; background: var(--raised); border-radius: var(--r-m); padding: 7px 12px 7px 7px; box-shadow: 0 4px 0 var(--edge); }
  .text { min-width: 0; }
  h4 { font: 800 15px/1.25 var(--font-body); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .text p { font-size: 13px; color: var(--ink-soft); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .fit { font-weight: 800; color: var(--good) !important; }
  .fit.low { color: var(--ink-soft) !important; }
  .use { background: var(--accent); color: var(--accent-ink); }
  .note { color: var(--ink-soft); }
  .small { font-size: 13px; }
</style>
