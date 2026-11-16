<script>
  import { api, windowApi } from "../lib/api.js";
  import { app, attempt, notify, refreshStatus, saveSettings } from "../lib/state.svelte.js";

  const textKeys = ["output_dir", "youtube_subdir", "spotify_subdir", "youtube_template", "spotify_template", "spotify_client_id"];
  let draft = $state(Object.fromEntries(textKeys.map((key) => [key, app.settings[key]])));
  const dirty = $derived(textKeys.some((key) => draft[key].trim() !== app.settings[key]));
  let saving = $state(false);
  let copied = $state(false);

  const spotify = $derived(app.status?.checks.find((check) => check.name === "Spotify"));
  const loginWaiting = $derived(app.status?.spotify_login_state === "waiting");

  async function save() {
    saving = true;
    const saved = await attempt(() => saveSettings(Object.fromEntries(textKeys.map((key) => [key, draft[key].trim()]))));
    saving = false;
    if (!saved) return;
    for (const key of textKeys) draft[key] = saved[key];
    notify("Settings saved.", "good");
    attempt(refreshStatus);
  }

  // Either/or choices are saved the moment they are pressed.
  async function set(key, value) {
    await attempt(() => saveSettings({ [key]: value }));
  }

  async function browse() {
    const folder = await windowApi()?.choose_folder();
    if (folder) draft.output_dir = folder;
  }

  async function login() {
    if (dirty) await save();
    const result = await attempt(api.spotifyLogin);
    if (result) {
      app.status.spotify_login_state = "waiting";
      notify("Your browser opened. Log in to Spotify there, then come back.");
    }
  }

  async function logout() {
    await attempt(api.spotifyLogout);
    await attempt(refreshStatus);
  }

  async function copyRedirect() {
    try {
      await navigator.clipboard.writeText(app.status.spotify_redirect_uri);
      copied = true;
      setTimeout(() => (copied = false), 1500);
    } catch {
      notify("Could not copy. Select the address and copy it by hand.", "problem");
    }
  }
</script>

<div class="screen">
  <div class="head">
    <h1>Settings</h1>
    <button class="big" onclick={save} disabled={!dirty || saving}>Save changes</button>
  </div>

  <div class="scroll">
    <section>
      <h2>Where downloads go</h2>
      <label class="field">
        <span>Output folder</span>
        <span class="line">
          <input class="well" spellcheck="false" bind:value={draft.output_dir}>
          {#if windowApi()}<button class="key" onclick={browse}>Browse</button>{/if}
        </span>
      </label>
      <div class="pair">
        <label class="field"><span>YouTube folder inside it</span><input class="well" spellcheck="false" bind:value={draft.youtube_subdir}></label>
        <label class="field"><span>Spotify folder inside it</span><input class="well" spellcheck="false" bind:value={draft.spotify_subdir}></label>
      </div>
      <div class="pair">
        <label class="field"><span>YouTube file names</span><input class="well" spellcheck="false" bind:value={draft.youtube_template}></label>
        <label class="field"><span>Spotify file names</span><input class="well" spellcheck="false" bind:value={draft.spotify_template}></label>
      </div>
      <p class="hint">File names can use {"{title}"}, {"{artist}"}, {"{album}"}, {"{track_number}"} and {"{year}"}.</p>
    </section>

    <section>
      <h2>Downloading</h2>
      <div class="field">
        <span>Save as, by default</span>
        <span class="line wrap">
          <span class="seg" role="group" aria-label="Default kind">
            <button aria-pressed={app.settings.mode === "audio"} onclick={() => set("mode", "audio")}>Audio</button>
            <button aria-pressed={app.settings.mode === "video"} onclick={() => set("mode", "video")}>Video</button>
          </span>
          <span class="seg" role="group" aria-label="Default audio format">
            <button aria-pressed={app.settings.audio_format === "original"} onclick={() => set("audio_format", "original")}>Original quality</button>
            <button aria-pressed={app.settings.audio_format === "mp3"} onclick={() => set("audio_format", "mp3")}>mp3</button>
          </span>
          <span class="seg" role="group" aria-label="Default video quality">
            {#each ["best", "1080p", "720p"] as quality (quality)}
              <button aria-pressed={app.settings.video_quality === quality} onclick={() => set("video_quality", quality)}>{quality === "best" ? "Best" : quality}</button>
            {/each}
          </span>
        </span>
      </div>
      <div class="field">
        <span>Downloads at the same time</span>
        <span class="line wrap">
          <span class="seg" role="group" aria-label="Downloads at the same time">
            {#each [1, 2, 3, 4] as count (count)}
              <button aria-pressed={app.settings.max_parallel_downloads === count} onclick={() => set("max_parallel_downloads", count)}>{count}</button>
            {/each}
          </span>
          <span class="hint">Takes effect the next time the app starts.</span>
        </span>
      </div>
    </section>

    <section>
      <h2>Spotify</h2>
      <label class="field">
        <span>Client ID of your Spotify app</span>
        <input class="well" spellcheck="false" autocomplete="off" bind:value={draft.spotify_client_id}>
      </label>
      <div class="field">
        <span>Redirect address to enter in the Spotify dashboard</span>
        <span class="line">
          <code>{app.status?.spotify_redirect_uri}</code>
          <button class="key" onclick={copyRedirect}>{copied ? "Copied" : "Copy"}</button>
        </span>
      </div>
      <div class="line wrap">
        {#if app.status?.spotify_logged_in}
          <b class="ok">Logged in.</b>
          <button class="key" onclick={logout}>Log out</button>
        {:else}
          <button class="key" onclick={login} disabled={loginWaiting || !draft.spotify_client_id.trim()}>{loginWaiting ? "Waiting for the browser" : "Log in to Spotify"}</button>
          {#if spotify && !spotify.ok}<span class="hint">{spotify.fix}</span>{/if}
        {/if}
      </div>
    </section>

    <section>
      <h2>Motion</h2>
      <div class="line wrap">
        <span class="seg" role="group" aria-label="Motion">
          <button aria-pressed={!app.settings.reduce_motion} onclick={() => set("reduce_motion", false)}>Playful</button>
          <button aria-pressed={app.settings.reduce_motion} onclick={() => set("reduce_motion", true)}>Reduced</button>
        </span>
        <span class="hint">Reduced turns the tilting and bouncing into plain instant changes.</span>
      </div>
    </section>

    <section>
      <h2>What the app needs</h2>
      <ul class="checks">
        {#each app.status?.checks ?? [] as check (check.name)}
          <li class:bad={!check.ok}>
            <b>{check.ok ? "OK" : check.required ? "Missing" : "Not set up"}</b>
            <span><strong>{check.name}</strong> {check.detail}{#if !check.ok && check.fix}<br><em>{check.fix}</em>{/if}</span>
          </li>
        {/each}
      </ul>
      <div class="line"><button class="key" onclick={() => attempt(refreshStatus)}>Check again</button></div>
    </section>
  </div>
</div>

<style>
  .scroll { overflow-y: auto; min-height: 0; flex: 1; display: grid; gap: 26px; align-content: start; padding: 2px 14px 16px 2px; }
  section { display: grid; gap: 12px; max-width: 760px; }
  h2 { font: 400 28px/1 var(--font-display); letter-spacing: .5px; }
  .field { display: grid; gap: 5px; min-width: 0; }
  .field > span:first-child { font-size: 14px; font-weight: 700; color: var(--ink-soft); }
  .pair { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .line { display: flex; gap: 10px; align-items: center; min-width: 0; }
  .line.wrap { flex-wrap: wrap; gap: 10px 14px; }
  .hint { color: var(--ink-soft); font-size: 14px; }
  code { font: 600 15px/1.4 Consolas, monospace; background: var(--edge); padding: 9px 12px; border-radius: var(--r-s); user-select: text; overflow-wrap: anywhere; }
  .ok { color: var(--good); }
  .checks { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
  .checks li { display: grid; grid-template-columns: 92px minmax(0, 1fr); gap: 12px; align-items: start; font-size: 14px; color: var(--ink-soft); overflow-wrap: anywhere; }
  .checks b { color: var(--good); font: 400 20px/1.2 var(--font-display); }
  .checks .bad b { color: var(--rose); }
  .checks strong { color: var(--ink); }
  .checks em { font-style: normal; color: var(--ink); }
  .head .big { font-size: 24px; padding: 8px 18px 10px; box-shadow: 0 5px 0 var(--edge); }
</style>
