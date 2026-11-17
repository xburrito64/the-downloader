<script>
  import { onMount } from "svelte";
  import { windowApi } from "./lib/api.js";
  import mascot from "./art/mascot.png";
  import { activeCount, app, failedCount, start } from "./lib/state.svelte.js";
  import Home from "./screens/Home.svelte";
  import Queue from "./screens/Queue.svelte";
  import Library from "./screens/Library.svelte";
  import Settings from "./screens/Settings.svelte";
  import MatchPicker from "./lib/MatchPicker.svelte";

  const tabs = [
    { id: "home", name: "Home", icon: "M12 3 3 11h3v9h5v-6h2v6h5v-9h3z" },
    { id: "queue", name: "Queue", icon: "M11 3h2v10h4l-5 6-5-6h4zM4 20h16v2H4z" },
    { id: "library", name: "Library", icon: "M3 4h8v8H3zM13 4h8v8h-8zM3 14h8v6H3zM13 14h8v6h-8z" },
    { id: "settings", name: "Settings", icon: "M10 2h4v3l2 1 2-2 3 3-2 2 1 2h3v4h-3l-1 2 2 2-3 3-2-2-2 1v3h-4v-3l-2-1-2 2-3-3 2-2-1-2H2v-4h3l1-2-2-2 3-3 2 2 2-1zM12 9a3 3 0 100 6 3 3 0 000-6z" },
  ];

  let inWindow = $state(false);   // false when the UI is opened in a normal browser
  let maximized = $state(false);
  const waiting = $derived(activeCount());
  const failed = $derived(failedCount());
  const missing = $derived((app.status?.checks ?? []).filter((check) => !check.ok && check.required));
  const ytdlp = $derived((app.status?.checks ?? []).find((check) => check.name === "yt-dlp")?.detail.split("  ")[0] ?? "");

  // The finish moment, part 1: the mascot hops and puffs out spores. Part 2 is the mushrooms below, part 3 the stamp on the row.
  let mascotEl = $state();
  let spores = $state([]);
  let sporeBatch = 0;
  let footHeight = $state(36);
  $effect(() => {
    if (!app.finished) return;
    mascotEl?.classList.remove("hop");
    void mascotEl?.offsetWidth;            // restart the hop if one is already playing
    mascotEl?.classList.add("hop");
    const batch = ++sporeBatch;
    spores = Array.from({ length: 9 }, (_, i) => {
      const angle = Math.PI * (0.1 + 0.8 * i / 8) + (Math.random() - 0.5) * 0.3;   // out to the sides and down
      const reach = 18 + Math.random() * 18;
      return { key: `-${i}`, pale: i % 3 === 0, dx: Math.round(-Math.cos(angle) * reach / 3) * 3, dy: Math.round(Math.sin(angle) * reach * 0.7 / 3) * 3 };
    });
    setTimeout(() => batch === sporeBatch && (spores = []), 1000);
  });

  // The mushrooms on the floor take turns: every few seconds one of them strolls a little way, hops or blinks.
  // In between nothing moves at all, so the window has nothing to redraw. (When they all moved all the time,
  // the window used about 14% of a processor core just for that.)
  let floorEl = $state();
  function replay(element, name, ms) {
    element.classList.remove(name);
    void element.offsetWidth;          // start the animation again from the beginning
    element.classList.add(name);
    setTimeout(() => element.classList.remove(name), ms);
  }
  function nextAct() {
    const walkers = floorEl?.querySelectorAll(".walker");
    const still = document.documentElement.classList.contains("resting") || app.settings?.reduce_motion;
    if (!walkers?.length || still) return;
    const walker = walkers[Math.floor(Math.random() * walkers.length)];
    const mush = walker.firstElementChild;
    const roll = Math.random();
    if (roll < 0.6) {
      // Anywhere between its spot and the end of its stretch (which points toward the middle, so none walks off).
      const range = Number(walker.dataset.range) || 60;
      const from = Number(walker.dataset.x) || 0;
      let to = Math.round(Math.random() * range);
      if (Math.abs(to - from) < 18) to = Math.abs(from) > Math.abs(range) / 2 ? 0 : range;
      const seconds = Math.min(3.2, 0.9 + Math.abs(to - from) / 40);
      walker.style.transition = `transform ${seconds}s ease-in-out`;
      walker.style.transform = `translateX(${to}px)`;
      walker.dataset.x = String(to);
      replay(mush, "walking", seconds * 1000);
    } else if (roll < 0.85) {
      replay(mush, "hopping", 600);
    } else {
      replay(mush, "blinking", 170);
    }
  }
  $effect(() => {
    let timer = 0;
    const tick = () => {
      nextAct();
      timer = setTimeout(tick, 1800 + Math.random() * 2400);
    };
    timer = setTimeout(tick, 2500);
    return () => clearTimeout(timer);
  });

  onMount(() => {
    start();
    const ready = () => (inWindow = Boolean(windowApi()));
    ready();
    window.addEventListener("pywebviewready", ready);
    // While another window is in front, the mushrooms stand still, so the app uses nothing then.
    const rest = () => document.documentElement.classList.toggle("resting", document.hidden || !document.hasFocus());
    rest();
    for (const name of ["focus", "blur"]) window.addEventListener(name, rest);
    document.addEventListener("visibilitychange", rest);
    return () => {
      window.removeEventListener("pywebviewready", ready);
      for (const name of ["focus", "blur"]) window.removeEventListener(name, rest);
      document.removeEventListener("visibilitychange", rest);
    };
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
  <div class="forest" aria-hidden="true"></div>
  <header class="titlebar pywebview-drag-region" ondblclick={inWindow ? toggleMaximize : null} role="presentation">
    <!-- the mascot: a 16 by 16 pixel mushroom, drawn by design/make_mascots.py -->
    <span class="puff">
      <img class="mascot" src={mascot} alt="" draggable="false" bind:this={mascotEl} onanimationend={() => mascotEl.classList.remove("hop")}>
      {#each spores as spore (spore.key)}<i class:pale={spore.pale} style:--dx="{spore.dx}px" style:--dy="{spore.dy}px"></i>{/each}
    </span>
    <h2>THE Downloader</h2>
    {#if inWindow}
      <div class="winkeys">
        <button aria-label="Minimise" onclick={() => windowApi()?.minimize()}><svg viewBox="0 0 12 12"><path d="M2 8h8v2H2z"/></svg></button>
        <button aria-label={maximized ? "Restore" : "Maximise"} title={maximized ? "Restore" : "Maximise"} onclick={toggleMaximize}>
          <!-- One square: make it fill the screen. Two overlapping squares: go back to the size before. -->
          {#if maximized}
            <svg viewBox="0 0 12 12"><path fill-rule="evenodd" d="M1.5 4.5h6v6h-6zM3 6v3h3V6zM4.5 1.5h6v6H9V3H4.5z"/></svg>
          {:else}
            <svg viewBox="0 0 12 12"><path fill-rule="evenodd" d="M2 2h8v8H2zM4 4v4h4V4z"/></svg>
          {/if}
        </button>
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
          <!-- Queue: how many are still to go, or else (in red) how many didn't download -->
          <span class="count" class:bad={tab.id === "queue" && !waiting && failed}>{tab.id === "queue" ? (waiting || failed || "") : tab.id === "settings" && missing.length ? "!" : ""}</span>
        </button>
      {/each}
    </nav>

    <main>
      <div class="veil" aria-hidden="true"></div>
      <!-- The finish moment, part 2: a mushroom grows on the forest floor for each finished download.
           The floor is a strip of its own at the bottom of every screen, where no content goes, so the
           mushrooms are always in plain view. They stand on the picture's dirt path, 60 to 75 screen
           pixels above the window's bottom edge, and wander along it. -->
      <div class="floor" aria-hidden="true" bind:this={floorEl}>
        {#each app.sprouts as sprout (sprout.id)}
          <div class="walker" style:left="{sprout.left}%" style:bottom="{60 + sprout.lift - footHeight}px" data-range={sprout.range}>
            <div class="mush"><img class="sprout" src={mascot} alt="" draggable="false"></div>
          </div>
        {/each}
      </div>
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

  <footer class="statusbar" bind:offsetHeight={footHeight}>
    <span class="msg" aria-live="polite">
      {#if app.notice}
        <b class={app.notice.kind}>{app.notice.text}</b>
      {:else if missing.length}
        <b class="problem">{missing.map((check) => check.name).join(" and ")} {missing.length === 1 ? "is" : "are"} missing.</b> Open Settings to see how to fix it.
      {:else if app.status}
        <b class="good">Ready.</b> {waiting ? `${waiting} in the queue.` : "Everything it needs is installed."}
      {/if}
    </span>
    {#if app.update?.can_update}
      <button class="fresh" onclick={() => (app.screen = "settings")}>New version ready</button>
    {:else}
      <span>{ytdlp ? `yt-dlp ${ytdlp}` : ""}</span>
    {/if}
  </footer>

  {#if app.matchFor}
    {#key app.matchFor.id}<MatchPicker job={app.matchFor} />{/key}
  {/if}

  {#if inWindow && !maximized}
    <div class="grip" onpointerdown={gripDown} onpointermove={gripMove} onpointerup={gripUp} onpointercancel={gripUp} aria-hidden="true"></div>
  {/if}
</div>

<style>
  .window { height: 100%; display: grid; grid-template-rows: auto minmax(0, 1fr) auto; background: var(--canopy); position: relative; isolation: isolate; }
  /* The forest: one small picture, shown at 3 screen pixels per art pixel, pinned to the bottom and repeated sideways.
     It has its own layer so that "pixelated" applies to it alone and not to cover pictures. */
  .forest {
    position: absolute; inset: 0; z-index: -1; pointer-events: none;
    background: url("./art/forest.png") repeat-x center bottom / 1920px 2160px; image-rendering: pixelated;
  }
  .window::after { /* still scanlines: an overlay, never an animation */
    content: ""; position: absolute; inset: 0; pointer-events: none; z-index: 5;
    background: repeating-linear-gradient(to bottom, var(--scan) 0 1px, transparent 1px 4px);
  }
  .titlebar { display: flex; align-items: center; gap: 12px; padding: 8px 10px 8px 16px; background: var(--panel-glass); }
  .titlebar h2 { font: 400 26px/1 var(--font-display); letter-spacing: .5px; flex: 1; pointer-events: none; }
  .puff { position: relative; flex: none; width: 32px; height: 26px; pointer-events: none; }
  /* The mascot file is the pixel art enlarged 8 times. Shown at 32 pixels with normal smoothing it is crisp at
     rest and moves fluidly; "pixelated" would snap every frame of a move to whole pixels and look jerky. */
  .mascot { position: absolute; left: 0; bottom: -2px; width: 32px; height: 32px; transform-origin: 50% 100%; will-change: transform; }
  .mascot:global(.hop) { animation: hop 640ms cubic-bezier(.3, .7, .4, 1); }
  @keyframes hop {
    0% { transform: none; }
    16% { transform: scale(1.12, .84); }                 /* crouch */
    44% { transform: translateY(-11px) scale(.92, 1.1); } /* up, stretched */
    70% { transform: scale(1.1, .88); }                  /* lands, squashed */
    86% { transform: scale(.97, 1.03); }
    100% { transform: none; }
  }
  .puff i { position: absolute; left: 14px; top: 8px; width: 4px; height: 4px; background: var(--accent); z-index: 7; animation: spore 900ms ease-out 140ms both; }
  .puff i.pale { background: var(--ink); }
  @keyframes spore {
    0% { transform: none; opacity: 1; }
    55% { transform: translate(var(--dx), var(--dy)); opacity: 1; }
    100% { transform: translate(calc(var(--dx) * 1.15), calc(var(--dy) + 8px)); opacity: 0; }  /* drifts down as it fades */
  }

  /* Behind a screen: the veil that keeps text readable, then the screen itself. The veil stops above the floor strip,
     so the forest floor shows plainly there. In front of everything: the floor with its mushrooms. */
  main { position: relative; }
  .veil {
    position: absolute; inset: 0;
    background: linear-gradient(to bottom, var(--veil) calc(100% - var(--floor) - 30px), transparent calc(100% - var(--floor) + 10px));
  }
  main:has(> :global(.screen.open)) .veil { background: linear-gradient(to bottom, var(--veil), var(--veil-thin) 70%, transparent calc(100% - var(--floor) + 10px)); }
  .floor { position: absolute; left: 0; right: 0; bottom: 0; height: var(--floor); overflow: hidden; pointer-events: none; z-index: 2; }

  /* A mushroom on the floor. The walker carries its position along the path; the mush inside waddles, hops or blinks. */
  .walker { position: absolute; width: 32px; height: 32px; margin-left: -16px; }
  .mush { position: relative; width: 32px; height: 32px; transform-origin: 50% 100%; }
  .mush:global(.walking) { animation: waddle 380ms ease-in-out infinite; }
  @keyframes waddle { 0%, 100% { transform: rotate(-3deg); } 50% { transform: translateY(-2px) rotate(3deg); } }
  .mush:global(.hopping) { animation: shroomhop 600ms cubic-bezier(.3, .7, .4, 1); }
  @keyframes shroomhop {
    16% { transform: scale(1.1, .86); }
    44% { transform: translateY(-9px) scale(.94, 1.08); }
    70% { transform: scale(1.08, .9); }
  }
  .mush::after { /* closed eyes: cream lids with a dark lash line, over the two eye pixels */
    content: ""; position: absolute; inset: 0; opacity: 0;
    background:
      linear-gradient(var(--edge), var(--edge)) 10px 21px / 2px 1px no-repeat, linear-gradient(var(--edge), var(--edge)) 20px 21px / 2px 1px no-repeat,
      linear-gradient(var(--ink), var(--ink)) 10px 18px / 2px 4px no-repeat, linear-gradient(var(--ink), var(--ink)) 20px 18px / 2px 4px no-repeat;
  }
  .mush:global(.blinking)::after { opacity: 1; }
  .sprout { display: block; width: 32px; height: 32px; transform-origin: 50% 100%; animation: sprout 560ms ease-out both; }
  /* Reduced motion: a walk that is under way just stops (the general rule only shortens animations). */
  :global(.calm) .mush { animation: none !important; }
  /* smooth, not in steps: stepped growth looked like a low frame rate (owner feedback, Nov 17, 2026) */
  @keyframes sprout { 0% { transform: scaleY(0); } 55% { transform: scaleY(1.15) scaleX(.9); } 78% { transform: scaleY(.94) scaleX(1.05); } 100% { transform: none; } }
  .winkeys { display: flex; gap: 8px; }
  .winkeys button {
    width: 34px; height: 24px; border: 0; border-radius: 6px; background: var(--raised); color: var(--ink); cursor: pointer;
    display: grid; place-items: center; box-shadow: 0 3px 0 var(--edge); transition: transform var(--quick), box-shadow var(--quick);
  }
  .winkeys button:active { transform: translateY(2px); box-shadow: 0 1px 0 var(--edge); }
  .winkeys svg { width: 12px; height: 12px; fill: currentColor; }
  .winkeys .close { background: var(--rose); color: var(--edge); }

  .body { display: grid; grid-template-columns: 96px minmax(0, 1fr); min-height: 0; }
  .rail { background: var(--panel-glass); padding: 12px 10px; display: flex; flex-direction: column; gap: 8px; }
  .tab {
    border: 0; background: none; cursor: pointer; border-radius: var(--r-m); padding: 10px 4px 6px; display: grid; justify-items: center; gap: 3px;
    color: var(--ink-soft); font-size: 13px; font-weight: 700; transition: transform var(--quick);
  }
  .tab svg { width: 26px; height: 26px; }
  .tab:hover { color: var(--ink); transform: translateY(-2px); }
  .tab[aria-current="page"] { background: var(--raised); color: var(--ink); box-shadow: 0 4px 0 var(--edge); }
  .count { font: 400 18px/1 var(--font-display); color: var(--accent); min-height: 18px; }
  .count.bad { color: var(--rose); }
  main { min-width: 0; min-height: 0; }
  main > :global(.screen) { position: relative; }

  .statusbar { display: flex; justify-content: space-between; gap: 16px; padding: 7px 26px 7px 18px; background: var(--panel-glass); color: var(--ink-soft); font-size: 14px; font-weight: 600; }
  .msg { min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .statusbar b { font-weight: 800; color: var(--ink); }
  .statusbar b.good { color: var(--good); }
  .statusbar b.problem { color: var(--rose); }
  .fresh { border: 0; cursor: pointer; padding: 0 10px; border-radius: 999px; background: var(--accent); color: var(--accent-ink); font: 800 13px/22px var(--font-body); }

  .grip { position: absolute; right: 0; bottom: 0; width: 22px; height: 22px; cursor: nwse-resize; z-index: 6; touch-action: none;
    background: linear-gradient(135deg, transparent 0 55%, var(--ink-soft) 55% 62%, transparent 62% 72%, var(--ink-soft) 72% 79%, transparent 79%); opacity: .6; }
</style>
