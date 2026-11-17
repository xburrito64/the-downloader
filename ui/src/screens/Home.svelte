<script>
  import { api } from "../lib/api.js";
  import { addJob, app, attempt, notify } from "../lib/state.svelte.js";
  import { duration, plural } from "../lib/format.js";
  import Cover from "../lib/Cover.svelte";
  import VirtualGrid from "../lib/VirtualGrid.svelte";

  let link = $state("");
  let reading = $state(false);
  let adding = $state(false);
  let problem = $state("");
  let found = $state.raw(null);      // what the link contains
  let picked = $state({});           // item number -> true
  let dealt = $state(false);         // cards slide in once after a link is read
  let dealing = $state(false);       // true only while they slide in, so later touches answer at once
  let gulp = $state(false);

  let mode = $state(app.settings.mode);
  let audioFormat = $state(app.settings.audio_format);
  let videoQuality = $state(app.settings.video_quality);

  const pickedCount = $derived(found ? found.items.reduce((n, item) => n + (picked[item.index] ? 1 : 0), 0) : 0);
  const canVideo = $derived(found?.provider === "youtube");
  const kindLabel = $derived(found ? `${found.provider === "spotify" ? "Spotify" : "YouTube"} ${found.kind}` : "");

  async function read() {
    const text = link.trim();
    if (!text || reading) return;
    reading = true;
    problem = "";
    gulp = true;
    setTimeout(() => (gulp = false), 140);
    try {
      const result = await api.resolve(text);
      const next = {};
      // Things that are already here start unpicked, so pressing Download never fetches them twice by accident.
      for (const item of result.items) next[item.index] = !item.already;
      picked = next;
      found = result;
      if (result.provider === "spotify") mode = "audio";
      dealt = false;
      dealing = true;
      // A timer, not an animation frame: frames stop while the window is minimised, and the cards must still appear.
      setTimeout(() => (dealt = true), 40);
      setTimeout(() => (dealing = false), 1000);
    } catch (error) {
      found = null;
      problem = error.message;
    }
    reading = false;
  }

  function pasted() {
    // A pasted link is read right away; typing waits for Enter or the button.
    setTimeout(read, 0);
  }

  function setAll(value) {
    const next = {};
    for (const item of found.items) next[item.index] = value;
    picked = next;
  }

  async function download() {
    if (!found || !pickedCount || adding) return;
    adding = true;
    const chosen = found.items.filter((item) => picked[item.index]);
    const result = await attempt(() => api.enqueue({
      resolve_id: found.resolve_id,
      indexes: chosen.map((item) => item.index),
      mode: canVideo ? mode : "audio",
      audio_format: audioFormat,
      video_quality: videoQuality,
      // Picking something that was downloaded before means "get it again".
      force: chosen.some((item) => item.already === "downloaded"),
    }));
    adding = false;
    if (!result) return;
    for (const job of result.jobs) if (job.result === "queued") addJob(job);
    app.settings.mode = canVideo ? mode : app.settings.mode;
    app.settings.audio_format = audioFormat;
    app.settings.video_quality = videoQuality;
    const skipped = result.skipped ? ` ${plural(result.skipped, "item")} skipped (already in the queue).` : "";
    notify(`${plural(result.queued, "download")} added to the queue.${skipped}`, result.queued ? "good" : "info");
    if (result.queued) {
      found = null;
      link = "";
      app.screen = "queue";
    }
  }

  // Cards lean toward the pointer. Done with CSS variables on the one card, so nothing else redraws.
  function tilt(event) {
    const card = event.currentTarget;
    const box = card.getBoundingClientRect();
    const x = (event.clientX - box.left) / box.width - 0.5;
    const y = (event.clientY - box.top) / box.height - 0.5;
    card.classList.add("tilting");
    card.style.setProperty("--ry", `${x * 14}deg`);
    card.style.setProperty("--rx", `${-y * 14}deg`);
    card.style.setProperty("--lift", "-6px");
  }
  function settle(event) {
    const card = event.currentTarget;
    card.classList.remove("tilting");
    card.style.setProperty("--ry", "0deg");
    card.style.setProperty("--rx", "0deg");
    card.style.setProperty("--lift", "0px");
  }
</script>

<div class="screen" class:open={!found}>
  <div class="slot" class:gulp>
    <input class="well" aria-label="Link" placeholder="Paste a Spotify or YouTube link" spellcheck="false" autocomplete="off"
      bind:value={link} onpaste={pasted} onkeydown={(event) => event.key === "Enter" && read()}>
    <button class="big" onclick={read} disabled={reading || !link.trim()}>{reading ? "Reading" : "Read link"}</button>
  </div>

  {#if problem}
    <p class="problem" role="alert">{problem}</p>
  {/if}

  {#if found}
    <div class="found">
      <span class="chip">{kindLabel}</span>
      <h3 title={found.title}>{found.title}</h3>
      <span class="sub">{pickedCount} of {found.count} picked</span>
      {#if found.count > 1}
        <button class="key" onclick={() => setAll(true)} disabled={pickedCount === found.count}>Pick all</button>
        <button class="key" onclick={() => setAll(false)} disabled={!pickedCount}>Pick none</button>
      {/if}
    </div>

    <div class="hand" class:dealt class:dealing>
      <VirtualGrid items={found.items} itemWidth={canVideo ? 216 : 140} itemHeight={canVideo ? 206 : 218} gap={16} keyOf={(item) => item.index}>
        {#snippet cell(item)}
          <button class="card" class:wide={canVideo} class:off={!picked[item.index]} aria-pressed={Boolean(picked[item.index])}
            style:--delay="{Math.min(item.index, 12) * 35}ms"
            onclick={() => (picked[item.index] = !picked[item.index])} onpointermove={tilt} onpointerleave={settle}>
            <Cover url={item.cover_url} label={item.title} wide={canVideo} />
            <h4 title={item.title}>{item.title}</h4>
            <p>{item.artist || " "}</p>
            <span class="foot">
              <span>{item.already === "downloaded" ? "Have it" : item.already === "in queue" ? "In queue" : duration(item.duration_seconds)}</span>
              <i class="tick"></i>
            </span>
          </button>
        {/snippet}
      </VirtualGrid>
    </div>

    <div class="choices">
      {#if canVideo}
        <div class="seg" role="group" aria-label="What to save">
          <button aria-pressed={mode === "audio"} onclick={() => (mode = "audio")}>Audio</button>
          <button aria-pressed={mode === "video"} onclick={() => (mode = "video")}>Video</button>
        </div>
      {/if}
      {#if mode === "audio" || !canVideo}
        <div class="seg" role="group" aria-label="Audio format">
          <button aria-pressed={audioFormat === "original"} onclick={() => (audioFormat = "original")}>Original quality</button>
          <button aria-pressed={audioFormat === "mp3"} onclick={() => (audioFormat = "mp3")}>mp3</button>
        </div>
      {:else}
        <div class="seg" role="group" aria-label="Video quality">
          <button aria-pressed={videoQuality === "best"} onclick={() => (videoQuality = "best")}>Best</button>
          <button aria-pressed={videoQuality === "1080p"} onclick={() => (videoQuality = "1080p")}>1080p</button>
          <button aria-pressed={videoQuality === "720p"} onclick={() => (videoQuality = "720p")}>720p</button>
        </div>
      {/if}
      <button class="big go" onclick={download} disabled={!pickedCount || adding}>Download {pickedCount || ""}</button>
    </div>
  {:else if !problem && !reading}
    <p class="empty">
      <strong>Paste a link to begin.</strong>
      YouTube videos and playlists, and Spotify tracks, albums and your own playlists.
    </p>
  {/if}
</div>

<style>
  .slot { display: flex; gap: 12px; align-items: stretch; padding-right: 10px; }
  .slot input { padding: 15px 20px; border-radius: var(--r-m); font-size: 17px; transition: transform var(--settle) var(--spring), border-color var(--quick); }
  .slot.gulp input { transform: scale(1.012, .9); transition-duration: 90ms; transition-timing-function: ease-out; }
  .slot .big { padding-top: 0; padding-bottom: 0; }

  .found { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 14px; padding-right: 10px; }
  .chip { background: var(--good); color: var(--on-good); font-weight: 800; font-size: 14px; padding: 4px 12px; border-radius: 999px; }
  .found h3 { font: 400 34px/1 var(--font-display); letter-spacing: .5px; min-width: 0; max-width: 100%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .sub { color: var(--ink-soft); margin-right: auto; }

  .hand { flex: 1; min-height: 0; display: flex; perspective: 900px; }
  .card {
    --rx: 0deg; --ry: 0deg; --lift: 0px;
    border: 0; text-align: left; display: block; width: 140px; height: 218px; background: var(--raised); border-radius: var(--r-m); padding: 8px 8px 10px;
    box-shadow: 0 6px 0 var(--edge); cursor: pointer; position: relative;
    opacity: 0; transform: translateY(40px) rotate(7deg) scale(.88);
  }
  .card.wide { width: 216px; height: 206px; }   /* videos: a 16:9 picture */
  .dealt .card {
    opacity: 1; transform: translateY(var(--lift)) rotateX(var(--rx)) rotateY(var(--ry));
    transition: transform var(--settle) var(--spring), opacity 200ms;
  }
  .dealing .card { transition-delay: var(--delay); }
  .dealt .card:global(.tilting) { transition: transform 90ms linear; }
  .dealt .card:active { transform: translateY(var(--lift)) scale(1.06, .94); transition-duration: 90ms; transition-delay: 0ms; }
  .dealt .card.off { opacity: .45; }
  .card h4 { margin: 8px 2px 0; font: 800 14px/1.25 var(--font-body); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .card p { margin: 1px 2px 0; font-size: 13px; color: var(--ink-soft); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .foot { margin: 7px 2px 0; height: 18px; display: flex; align-items: center; justify-content: space-between; font: 400 19px/1 var(--font-display); color: var(--ink-soft); }
  .tick { width: 18px; height: 18px; border-radius: 5px; background: var(--accent); display: grid; place-items: center; }
  .tick::after { content: ""; width: 9px; height: 5px; border-left: 3px solid var(--accent-ink); border-bottom: 3px solid var(--accent-ink); transform: rotate(-45deg) translateY(-1px); }
  .off .tick { background: var(--panel); }
  .off .tick::after { display: none; }

  .choices { display: flex; flex-wrap: wrap; gap: 12px 18px; align-items: center; padding: 4px 10px 6px 0; }
  .go { margin-left: auto; }
</style>
