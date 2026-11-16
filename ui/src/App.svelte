<script>
  import { onMount } from "svelte";
  import { windowApi } from "./lib/api.js";
  import { activeCount, app, start } from "./lib/state.svelte.js";
  import Home from "./screens/Home.svelte";
  import Queue from "./screens/Queue.svelte";
  import Library from "./screens/Library.svelte";
  import Settings from "./screens/Settings.svelte";

  const tabs = [
    { id: "home", name: "Home", icon: "M12 3 3 11h3v9h5v-6h2v6h5v-9h3z" },
    { id: "queue", name: "Queue", icon: "M11 3h2v10h4l-5 6-5-6h4zM4 20h16v2H4z" },
    { id: "library", name: "Library", icon: "M3 4h8v8H3zM13 4h8v8h-8zM3 14h8v6H3zM13 14h8v6h-8z" },
    { id: "settings", name: "Settings", icon: "M10 2h4v3l2 1 2-2 3 3-2 2 1 2h3v4h-3l-1 2 2 2-3 3-2-2-2 1v3h-4v-3l-2-1-2 2-3-3 2-2-1-2H2v-4h3l1-2-2-2 3-3 2 2 2-1zM12 9a3 3 0 100 6 3 3 0 000-6z" },
  ];

  let inWindow = $state(false);   // false when the UI is opened in a normal browser
  let maximized = $state(false);
  const waiting = $derived(activeCount());
  const missing = $derived((app.status?.checks ?? []).filter((check) => !check.ok && check.required));
  const ytdlp = $derived((app.status?.checks ?? []).find((check) => check.name === "yt-dlp")?.detail.split("  ")[0] ?? "");

  onMount(() => {
    start();
    const ready = () => (inWindow = Boolean(windowApi()));
    ready();
    window.addEventListener("pywebviewready", ready);
    return () => window.removeEventListener("pywebviewready", ready);
  });

  async function toggleMaximize() {
    maximized = Boolean(await windowApi()?.toggle_maximize());
  }

  // A window without a frame has no edges to drag, so the corner grip resizes it.
  let grip = null;
  let pending = 0;
  function gripDown(event) {
    grip = { x: event.screenX, y: event.screenY, width: window.outerWidth, height: window.outerHeight };
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function gripMove(event) {
    if (!grip || pending) return;
    const width = grip.width + event.screenX - grip.x;
    const height = grip.height + event.screenY - grip.y;
    pending = requestAnimationFrame(() => {
      pending = 0;
      windowApi()?.resize(width, height);
    });
  }
  function gripUp() {
    grip = null;
  }
</script>

<div class="window">
  <header class="titlebar pywebview-drag-region" ondblclick={inWindow ? toggleMaximize : null} role="presentation">
    <!-- placeholder mascot: a small original pixel wisp. This spot is for the owner's own art (milestone 8). -->
    <svg class="wisp" viewBox="0 0 8 8" shape-rendering="crispEdges" aria-hidden="true">
      <path fill="var(--accent)" d="M3 0h2v1h1v1h1v3h-1v1h-1v1h-2v-1h-1v-1h-1v-3h1v-1h1z"/>
      <path fill="var(--edge)" d="M2 3h1v1h-1zM5 3h1v1h-1z"/>
      <path fill="var(--ink)" d="M3 1h1v1h-1z"/>
    </svg>
    <h2>THE Downloader</h2>
    {#if inWindow}
      <div class="winkeys">
        <button aria-label="Minimise" onclick={() => windowApi()?.minimize()}><svg viewBox="0 0 12 12"><path d="M2 8h8v2H2z"/></svg></button>
        <button aria-label={maximized ? "Restore" : "Maximise"} onclick={toggleMaximize}><svg viewBox="0 0 12 12"><path fill-rule="evenodd" d="M2 2h8v8H2zM4 4v4h4V4z"/></svg></button>
        <button class="close" aria-label="Close" onclick={() => windowApi()?.close()}><svg viewBox="0 0 12 12"><path d="M2 3.5 3.5 2 6 4.5 8.500 2 10 3.5 7.500 6 10 8.500 8.500 10 6 7.500 3.5 10 2 8.500 4.5 6z"/></svg></button>
      </div>
    {/if}
  </header>

  <div class="body">
    <nav class="rail" aria-label="Screens">
      {#each tabs as tab (tab.id)}
        <button class="tab" aria-current={app.screen === tab.id ? "page" : null} onclick={() => (app.screen = tab.id)}>
          <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path fill-rule="evenodd" d={tab.icon}/></svg>
          {tab.name}
          <span class="count">{tab.id === "queue" && waiting ? waiting : tab.id === "settings" && missing.length ? "!" : ""}</span>
        </button>
      {/each}
    </nav>

    <main>
      {#if app.loadError}
        <div class="screen"><p class="empty"><strong>The app could not start.</strong>{app.loadError}</p></div>
      {:else if !app.settings}
        <div class="screen"></div>
      {:else if app.screen === "home"}
        <Home />
      {:else if app.screen === "queue"}
        <Queue />
      {:else if app.screen === "library"}
        <Library />
      {:else}
        <Settings />
      {/if}
    </main>
  </div>

  <footer class="statusbar">
    <span class="msg" aria-live="polite">
      {#if app.notice}
        <b class={app.notice.kind}>{app.notice.text}</b>
      {:else if missing.length}
        <b class="problem">{missing.map((check) => check.name).join(" and ")} {missing.length === 1 ? "is" : "are"} missing.</b> Open Settings to see how to fix it.
      {:else if app.status}
        <b class="good">Ready.</b> {waiting ? `${waiting} in the queue.` : "Everything it needs is installed."}
      {/if}
    </span>
    <span>{ytdlp ? `yt-dlp ${ytdlp}` : ""}</span>
  </footer>

  {#if inWindow && !maximized}
    <div class="grip" onpointerdown={gripDown} onpointermove={gripMove} onpointerup={gripUp} onpointercancel={gripUp} aria-hidden="true"></div>
  {/if}
</div>

<style>
  .window { height: 100%; display: grid; grid-template-rows: auto minmax(0, 1fr) auto; background: var(--base); position: relative; }
  .window::after { /* still scanlines: an overlay, never an animation */
    content: ""; position: absolute; inset: 0; pointer-events: none; z-index: 5;
    background: repeating-linear-gradient(to bottom, var(--scan) 0 1px, transparent 1px 4px);
  }
  .titlebar { display: flex; align-items: center; gap: 12px; padding: 8px 10px 8px 16px; background: var(--panel); }
  .titlebar h2 { font: 400 26px/1 var(--font-display); letter-spacing: .5px; flex: 1; pointer-events: none; }
  .wisp { width: 22px; height: 22px; flex: none; pointer-events: none; }
  .winkeys { display: flex; gap: 8px; }
  .winkeys button {
    width: 34px; height: 24px; border: 0; border-radius: 6px; background: var(--raised); color: var(--ink); cursor: pointer;
    display: grid; place-items: center; box-shadow: 0 3px 0 var(--edge); transition: transform var(--quick), box-shadow var(--quick);
  }
  .winkeys button:active { transform: translateY(2px); box-shadow: 0 1px 0 var(--edge); }
  .winkeys svg { width: 12px; height: 12px; fill: currentColor; }
  .winkeys .close { background: var(--rose); color: var(--edge); }

  .body { display: grid; grid-template-columns: 96px minmax(0, 1fr); min-height: 0; }
  .rail { background: var(--panel); padding: 12px 10px; display: flex; flex-direction: column; gap: 8px; }
  .tab {
    border: 0; background: none; cursor: pointer; border-radius: var(--r-m); padding: 10px 4px 6px; display: grid; justify-items: center; gap: 3px;
    color: var(--ink-soft); font-size: 13px; font-weight: 700; transition: transform var(--quick);
  }
  .tab svg { width: 26px; height: 26px; }
  .tab:hover { color: var(--ink); transform: translateY(-2px); }
  .tab[aria-current="page"] { background: var(--raised); color: var(--ink); box-shadow: 0 4px 0 var(--edge); }
  .count { font: 400 18px/1 var(--font-display); color: var(--accent); min-height: 18px; }
  main { min-width: 0; min-height: 0; }

  .statusbar { display: flex; justify-content: space-between; gap: 16px; padding: 7px 26px 7px 18px; background: var(--panel); color: var(--ink-soft); font-size: 14px; font-weight: 600; }
  .msg { min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .statusbar b { font-weight: 800; color: var(--ink); }
  .statusbar b.good { color: var(--good); }
  .statusbar b.problem { color: var(--rose); }

  .grip { position: absolute; right: 0; bottom: 0; width: 22px; height: 22px; cursor: nwse-resize; z-index: 6; touch-action: none;
    background: linear-gradient(135deg, transparent 0 55%, var(--ink-soft) 55% 62%, transparent 62% 72%, var(--ink-soft) 72% 79%, transparent 79%); opacity: .6; }
</style>
