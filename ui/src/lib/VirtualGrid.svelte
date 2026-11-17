<script>
  // Shows a long list while only building the rows that are on screen.
  // A playlist with a thousand songs costs the window about as much as one with thirty.
  let { items, itemWidth = 0, itemHeight, gap = 16, keyOf = (item) => item.id, cell, onnearend = null } = $props();

  let viewport;
  let scrollTop = $state(0);
  let width = $state(0);
  let height = $state(0);

  const columns = $derived(itemWidth ? Math.max(1, Math.floor((width + gap) / (itemWidth + gap))) : 1);
  const rowHeight = $derived(itemHeight + gap);
  const rows = $derived(Math.ceil(items.length / columns));
  const first = $derived(Math.max(0, Math.floor(scrollTop / rowHeight) - 2));
  const last = $derived(Math.min(rows, Math.ceil((scrollTop + height) / rowHeight) + 2));
  const visible = $derived(items.slice(first * columns, last * columns));

  function scrolled() {
    scrollTop = viewport.scrollTop;
  }

  $effect(() => {
    if (onnearend && rows > 0 && last >= rows - 2) onnearend();
  });
</script>

<div class="viewport fade-out" bind:this={viewport} bind:clientWidth={width} bind:clientHeight={height} onscroll={scrolled}>
  <div class="track" style:height="{Math.max(0, rows * rowHeight - gap)}px">
    <div
      class="rows"
      style:transform="translateY({first * rowHeight}px)"
      style:grid-template-columns={itemWidth ? `repeat(${columns}, ${itemWidth}px)` : "1fr"}
      style:grid-auto-rows="{itemHeight}px"
      style:gap="{gap}px"
    >
      {#each visible as item, i (keyOf(item))}
        {@render cell(item, first * columns + i)}
      {/each}
    </div>
  </div>
</div>

<style>
  .viewport { overflow-y: auto; min-height: 0; flex: 1; padding: 6px 10px 12px 2px; }
  .track { position: relative; }
  .rows { display: grid; position: absolute; left: 0; right: 0; top: 0; }
</style>
