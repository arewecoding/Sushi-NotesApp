<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { Tool, BackgroundConfig } from './types';
  import { DEFAULTS } from './config';
  import { featureFlags } from './stores';

  export let bgConfig: BackgroundConfig = { type: 'none', color: '#d0d0d0', spacing: 20 };
  let showBackgroundPicker = false;
  const patternTypes = ["none", "dots", "grid", "lines", "ruled", "dotted", "cornell", "music_staff", "isometric"] as const;

  function setBgType(t: typeof patternTypes[number]) {
    bgConfig.type = t;
    dispatch('action', 'bg_update');
  }

  function onBgColorInput(e: Event) {
    bgConfig.color = (e.target as HTMLInputElement).value;
    dispatch('action', 'bg_update');
  }

  function onBgSpacingInput(e: Event) {
    bgConfig.spacing = parseInt((e.target as HTMLInputElement).value, 10);
    dispatch('action', 'bg_update');
  }

  function renderPatternPreview(node: HTMLCanvasElement, params: { type: string, color: string, spacing: number }) {
    function draw(p: { type: string, color: string, spacing: number }) {
      const ctx = node.getContext('2d');
      if (!ctx) return;
      const w = node.width;
      const h = node.height;
      ctx.clearRect(0, 0, w, h);
      if (p.type === 'none') return;
      
      const config = { type: p.type as any, color: p.color, spacing: p.spacing };
      ctx.save();
      ctx.fillStyle = config.color;
      ctx.strokeStyle = config.color;
      ctx.lineWidth = 1;

      const spacing = config.spacing;
      ctx.beginPath();

      if (config.type === "dots") {
        const radius = 1;
        for (let x = 0; x <= w; x += spacing) {
          for (let y = 0; y <= h; y += spacing) {
            ctx.moveTo(x + radius, y);
            ctx.arc(x, y, radius, 0, Math.PI*2);
          }
        }
        ctx.fill();
      } else if (config.type === "dotted") {
        const radius = 0.5;
        const s = spacing * 0.5;
        for (let x = 0; x <= w; x += s) {
          for (let y = 0; y <= h; y += s) {
            ctx.moveTo(x + radius, y);
            ctx.arc(x, y, radius, 0, Math.PI*2);
          }
        }
        ctx.fill();
      } else if (config.type === "grid") {
        for (let x = 0; x <= w; x += spacing) { ctx.moveTo(x, 0); ctx.lineTo(x, h); }
        for (let y = 0; y <= h; y += spacing) { ctx.moveTo(0, y); ctx.lineTo(w, y); }
        ctx.stroke();
      } else if (config.type === "lines" || config.type === "ruled" || config.type === "cornell") {
        for (let y = 0; y <= h; y += spacing) { ctx.moveTo(0, y); ctx.lineTo(w, y); }
        ctx.stroke();
        if (config.type === "ruled" || config.type === "cornell") {
           ctx.beginPath();
           ctx.lineWidth = 2;
           ctx.strokeStyle = "rgba(255, 170, 170, 0.6)";
           const mx = config.type === "ruled" ? spacing * 3 : 12; // arbitrary mini scale
           ctx.moveTo(mx, 0); ctx.lineTo(mx, h);
           ctx.stroke();
        }
      } else if (config.type === "isometric") {
        ctx.globalAlpha = 0.7;
        const hSpace = spacing * Math.sqrt(3);
        for (let y = -spacing; y <= h + spacing; y += spacing) { ctx.moveTo(0, y); ctx.lineTo(w, y); }
        const diagW = 80;
        const dx = Math.cos(Math.PI/6) * diagW;
        const dy = Math.sin(Math.PI/6) * diagW;
        for (let x = -diagW; x <= w + diagW; x += spacing) {
           ctx.moveTo(x, -diagW); ctx.lineTo(x + dx, -diagW + dy);
           ctx.moveTo(x, h + diagW); ctx.lineTo(x + dx, h + diagW - dy);
        }
        ctx.stroke();
      } else if (config.type === "music_staff") {
        const gs = spacing * 4;
        const ls = spacing * 0.6;
        for (let y = 0; y <= h; y += gs) {
          for (let i = 0; i < 5; i++) {
             const ly = y + i * ls;
             ctx.moveTo(0, ly); ctx.lineTo(w, ly);
          }
        }
        ctx.stroke();
      }
      ctx.restore();
    }
    draw(params);
    return {
      update(newParams: { type: string, color: string, spacing: number }) { draw(newParams); }
    };
  }

  export let tool: Tool = 'pen';
  export let color: string = DEFAULTS.COLOR;
  export let size: number = DEFAULTS.STROKE_SIZE;
  export let canUndo: boolean = false;
  export let canRedo: boolean = false;
  export let selectedColor: string | null = null;
  export let isNotebookMode: boolean = false;
  export let isDirty: boolean = false;

  const dispatch = createEventDispatcher<{action: string}>();

  const allTools: Tool[] = ['pen', 'highlighter', 'marker', 'eraser', 'cursor', 'select', 'text'];
  $: tools = allTools.filter(t => {
    if (t === 'text' && $featureFlags.enable_text_tool === false) return false;
    if (t === 'select' && $featureFlags.enable_select_tool === false) return false;
    return true;
  });

  const colors = ['#1a1a1a', '#e53935', '#43a047', '#1e88e5', '#fdd835'];

  // Show selection color when strokes are selected, otherwise pen color
  $: displayColor = selectedColor !== null ? selectedColor : color;
  $: isMixed = selectedColor === 'mixed';
  $: hasSelection = selectedColor !== null;

  function onPresetClick(c: string) {
    if (tool === 'text') {
      dispatch('action', `textstyle:${JSON.stringify({ color: c })}`);
    } else if (hasSelection) {
      dispatch('action', `color:commit:${c}`);
    } else {
      color = c;
    }
  }

  function onPickerInput(e: Event) {
    const val = (e.target as HTMLInputElement).value;
    if (tool === 'text') {
      dispatch('action', `textstyle:${JSON.stringify({ color: val })}`);
    } else if (hasSelection) {
      dispatch('action', `color:preview:${val}`);
    } else {
      color = val;
    }
  }

  function onPickerChange(e: Event) {
    const val = (e.target as HTMLInputElement).value;
    if (tool === 'text') {
      dispatch('action', `textstyle:${JSON.stringify({ color: val })}`);
    } else if (hasSelection) {
      dispatch('action', `color:commit:${val}`);
    } else {
      color = val;
    }
  }

  // Text tool font options
  let textFontFamily = DEFAULTS.FONT_FAMILY;
  export let textFontSize: number = DEFAULTS.FONT_SIZE;
  let textBold = false;
  let textItalic = false;

  const fontFamilies = ['system-ui', 'Georgia', 'Times New Roman', 'Courier New', 'Arial'];

  function onTextStyleChange() {
    dispatch('action', `textstyle:${JSON.stringify({
      font_family: textFontFamily,
      font_size: textFontSize,
      font_weight: textBold ? 700 : 400,
      font_style: textItalic ? 'italic' : 'normal',
      color: color,
    })}`);
  }
</script>

<div class="toolbar">
  <div class="section">
    <h4>Tools</h4>
    <div class="row">
      {#each tools as t}
        <button class:active={tool === t} on:click={() => (tool = t)}>
          {t}
        </button>
      {/each}
    </div>
  </div>

  <div class="section">
    <h4>Color{hasSelection ? ' (selection)' : ''}</h4>
    <div class="row">
      {#each colors as c}
        <button
          class="color-btn"
          class:active={displayColor === c && !isMixed}
          style="background-color: {c}"
          on:click={() => onPresetClick(c)}
          aria-label={c}
        ></button>
      {/each}
      <div class="picker-container">
        {#if isMixed}
          <div class="color-btn mixed-swatch" title="Mixed colors"></div>
        {/if}
        <input
          type="color"
          value={isMixed ? '#888888' : displayColor}
          on:input={onPickerInput}
          on:change={onPickerChange}
          class="color-picker"
          class:hidden-picker={isMixed}
        />
      </div>
    </div>
  </div>

  <div class="section">
    <h4>Size: {size}px</h4>
    <input type="range" min="1" max="40" bind:value={size} />
  </div>

  <div class="section">
    <h4>Actions</h4>
    <div class="row">
      <button disabled={!canUndo} on:click={() => dispatch('action', 'undo')}>Undo</button>
      <button disabled={!canRedo} on:click={() => dispatch('action', 'redo')}>Redo</button>
      {#if $featureFlags.enable_notebooks !== false}
        <button on:click={() => dispatch('action', 'new_notebook')}>New Notebook</button>
      {/if}
      <button class:dirty-btn={isNotebookMode && isDirty} on:click={() => dispatch('action', 'save')}>
        Save{isNotebookMode && isDirty ? ' •' : ''}
      </button>
      <button on:click={() => dispatch('action', 'load')}>Load</button>
      <button on:click={() => dispatch('action', 'export_svg')}>Export SVG</button>
    </div>
  </div>

  {#if $featureFlags.enable_background_patterns !== false}
    <div class="section toolbar-bg-picker" style="position: relative;">
      <h4>Background</h4>
      <button on:click={() => showBackgroundPicker = !showBackgroundPicker}>
        Pattern: {bgConfig.type}
      </button>
      {#if showBackgroundPicker}
         <div class="bg-popover">
           <div class="bg-grid">
             {#each patternTypes as pType}
               <button class="bg-preview-btn" class:active={bgConfig.type === pType} on:click={() => setBgType(pType)} title={pType}>
                 <canvas width="40" height="40" use:renderPatternPreview={{type: pType, color: bgConfig.color, spacing: bgConfig.spacing}}></canvas>
               </button>
             {/each}
           </div>
           <div class="bg-controls">
             <label class="bg-control-row">
               <span>Color</span>
               <input type="color" value={bgConfig.color} on:input={onBgColorInput} class="bg-color-picker" />
             </label>
             <label class="bg-control-row">
               <span>Spacing ({bgConfig.spacing})</span>
               <input type="range" min="10" max="60" value={bgConfig.spacing} on:input={onBgSpacingInput} />
             </label>
           </div>
         </div>
      {/if}
    </div>
  {/if}

  {#if tool === 'text'}
    <div class="section">
      <h4>Font</h4>
      <select bind:value={textFontFamily} on:change={onTextStyleChange}>
        {#each fontFamilies as f}
          <option value={f}>{f}</option>
        {/each}
      </select>
      <div class="row">
        <label for="text-font-size" style="font-size:12px;flex:1;">Size:</label>
        <input id="text-font-size" type="number" min="8" max="999" bind:value={textFontSize} on:input={onTextStyleChange} on:change={onTextStyleChange} style="width:60px;font-size:12px;padding:4px 6px;border:1px solid #ddd;border-radius:4px;" />
        <span style="font-size:12px;">px</span>
      </div>
      <div class="row">
        <button class:active={textBold} on:click={() => { textBold = !textBold; onTextStyleChange(); }} on:mousedown|preventDefault>
          <b>B</b>
        </button>
        <button class:active={textItalic} on:click={() => { textItalic = !textItalic; onTextStyleChange(); }} on:mousedown|preventDefault>
          <i>I</i>
        </button>
      </div>
    </div>
  {/if}
</div>

<style>
  .toolbar {
    position: fixed;
    top: 20px;
    left: 20px;
    background: white;
    padding: 16px;
    border-radius: 12px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    z-index: 100;
    display: flex;
    flex-direction: column;
    gap: 16px;
    width: 200px;
  }

  .section {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  h4 {
    margin: 0;
    font-size: 12px;
    text-transform: uppercase;
    color: #666;
  }

  .row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  button {
    padding: 6px 10px;
    border: 1px solid #ddd;
    background: #fff;
    border-radius: 6px;
    cursor: pointer;
    font-size: 12px;
    flex: 1;
    min-width: 60px;
  }

  button.active {
    background: #e0e0e0;
    border-color: #999;
    font-weight: bold;
  }

  .color-btn {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    border: 2px solid transparent;
    padding: 0;
    min-width: 0;
  }

  .color-btn.active {
    border-color: #000;
  }

  .mixed-swatch {
    background: repeating-linear-gradient(
      45deg,
      #aaa,
      #aaa 4px,
      #eee 4px,
      #eee 8px
    );
  }

  .color-picker {
    width: 24px;
    height: 24px;
    padding: 0;
    border: none;
    border-radius: 4px;
    cursor: pointer;
  }

  .picker-container {
    position: relative;
    width: 24px;
    height: 24px;
  }

  .hidden-picker {
    position: absolute;
    top: 0;
    left: 0;
    opacity: 0;
    width: 100%;
    height: 100%;
    cursor: pointer;
  }

  .bg-popover {
    position: absolute;
    top: 0;
    left: 105%;
    background: white;
    padding: 12px;
    border-radius: 8px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.15);
    z-index: 200;
    width: 200px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .bg-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
  }

  .bg-preview-btn {
    padding: 2px;
    width: 48px;
    height: 48px;
    border: 2px solid transparent;
    background: #f9f9f9;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
  }

  .bg-preview-btn.active {
    border-color: #000;
    background: #eee;
  }

  .bg-preview-btn canvas {
    width: 40px;
    height: 40px;
    background: white;
    border: 1px solid #ddd;
    border-radius: 2px;
  }

  .bg-controls {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .bg-control-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 12px;
  }

  .bg-control-row input[type="range"] {
    width: 80px;
  }

  .bg-color-picker {
    width: 24px;
    height: 24px;
    padding: 0;
    border: none;
    border-radius: 4px;
    cursor: pointer;
  }
</style>
