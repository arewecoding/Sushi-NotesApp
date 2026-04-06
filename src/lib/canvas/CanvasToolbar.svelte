<script lang="ts">
  /**
   * CanvasToolbar.svelte
   * ====================
   * Horizontal toolbar for the canvas tab, styled to match the Notes app's
   * top bar (h-12, bg-neutral-900, border-b border-neutral-800).
   *
   * All tool/color/size state is bound from the parent CanvasView.
   */
  import { createEventDispatcher } from 'svelte';
  import {
    Pen,
    Highlighter,
    PaintBucket,
    Eraser,
    MousePointer2,
    Type,
    Move,
    Undo2,
    Redo2,
    Grid,
    Bold,
    Italic,
  } from 'lucide-svelte';
  import type { Tool, BackgroundConfig } from './types';
  import { DEFAULTS } from './config';

  export let tool: Tool = 'pen';
  export let color: string = DEFAULTS.COLOR;
  export let size: number = DEFAULTS.STROKE_SIZE;
  export let canUndo: boolean = false;
  export let canRedo: boolean = false;
  export let selectedColor: string | null = null;
  export let activeTextStyle: any = { fontFamily: DEFAULTS.FONT_FAMILY, fontSize: DEFAULTS.FONT_SIZE, fontWeight: DEFAULTS.FONT_WEIGHT, fontStyle: DEFAULTS.FONT_STYLE, color: DEFAULTS.COLOR };
  export let bgConfig: BackgroundConfig;

  let showBgMenu = false;

  const dispatch = createEventDispatcher<{ action: string }>();

  const toolDefs: { id: Tool; icon: any; label: string }[] = [
    { id: 'pen',         icon: Pen,           label: 'Pen' },
    { id: 'highlighter', icon: Highlighter,   label: 'Highlighter' },
    { id: 'marker',      icon: PaintBucket,   label: 'Marker' },
    { id: 'eraser',      icon: Eraser,        label: 'Eraser' },
    { id: 'select',      icon: MousePointer2, label: 'Select' },
    { id: 'text',        icon: Type,          label: 'Text' },
    { id: 'cursor',      icon: Move,          label: 'Pan' },
  ];

  const colors = ['#1a1a1a', '#e53935', '#43a047', '#1e88e5', '#fdd835', '#ff9800', '#9c27b0', '#ffffff'];

  $: displayColor = selectedColor !== null ? selectedColor : color;
  $: isMixed = selectedColor === 'mixed';
  $: hasSelection = selectedColor !== null;

  function onPresetClick(c: string) {
    if (hasSelection) {
      dispatch('action', `color:commit:${c}`);
    } else {
      color = c;
    }
  }

  function onPickerInput(e: Event) {
    const val = (e.target as HTMLInputElement).value;
    if (hasSelection) {
      dispatch('action', `color:preview:${val}`);
    } else {
      color = val;
    }
  }

  function onPickerChange(e: Event) {
    const val = (e.target as HTMLInputElement).value;
    if (hasSelection) {
      dispatch('action', `color:commit:${val}`);
    } else {
      color = val;
    }
  }

  const bgPatterns = [
    { id: 'none', label: 'Blank' },
    { id: 'dots', label: 'Dots' },
    { id: 'grid', label: 'Grid' },
    { id: 'lines', label: 'Lines' },
    { id: 'ruled', label: 'Ruled' }
  ] as const;

  function setBgPattern(type: BackgroundConfig['type']) {
    bgConfig = { ...bgConfig, type };
    showBgMenu = false;
  }
</script>

<div class="canvas-toolbar">
  <!-- Tool group -->
  <div class="tool-group">
    {#each toolDefs as t}
      <button
        class="tool-btn"
        class:active={tool === t.id}
        title={t.label}
        on:click={() => (tool = t.id)}
      >
        <svelte:component this={t.icon} size={16} />
      </button>
    {/each}
  </div>

  <div class="divider"></div>

  <!-- Color group -->
  <div class="tool-group">
    {#each colors as c}
      <button
        class="color-swatch"
        class:active={displayColor === c && !isMixed}
        style="--swatch-color: {c};"
        title={c}
        on:click={() => onPresetClick(c)}
      ></button>
    {/each}
    <div class="picker-wrapper">
      <input
        type="color"
        value={isMixed ? '#888888' : displayColor}
        on:input={onPickerInput}
        on:change={onPickerChange}
        class="color-input"
        title="Custom color"
      />
    </div>
  </div>

  <div class="divider"></div>

  <!-- Config / Size Section -->
  {#if tool === 'text'}
    <div class="tool-group text-config-group">
      <select
        class="font-select"
        value={activeTextStyle.fontFamily}
        on:change={(e) => dispatch('action', `textstyle:{"font_family":"${e.currentTarget.value}"}`)}
        title="Font Family"
      >
        <option value="system-ui">System</option>
        <option value="serif">Serif</option>
        <option value="monospace">Monospace</option>
      </select>
      
      <button
        class="tool-btn text-style-btn"
        class:active={activeTextStyle.fontWeight === 700}
        title="Bold"
        on:click={() => dispatch('action', `textstyle:{"font_weight":${activeTextStyle.fontWeight === 700 ? 400 : 700}}`)}
      >
        <Bold size={14} />
      </button>
      
      <button
        class="tool-btn text-style-btn"
        class:active={activeTextStyle.fontStyle === 'italic'}
        title="Italic"
        on:click={() => dispatch('action', `textstyle:{"font_style":"${activeTextStyle.fontStyle === 'italic' ? 'normal' : 'italic'}"}`)}
      >
        <Italic size={14} />
      </button>

      <div class="divider mx-1"></div>

      <span class="size-label">Size</span>
      <input
        type="number"
        min="8"
        max="999"
        value={activeTextStyle.fontSize}
        on:input={(e) => dispatch('action', `textstyle:{"font_size":${e.currentTarget.value}}`)}
        on:change={(e) => dispatch('action', `textstyle:{"font_size":${e.currentTarget.value}}`)}
        class="size-number-input"
      />
    </div>
  {:else if ['pen', 'highlighter', 'marker', 'eraser'].includes(tool)}
    <div class="tool-group size-group">
      <span class="size-label">{size}px</span>
      <input
        type="range"
        min="1"
        max="40"
        bind:value={size}
        class="size-slider"
      />
    </div>
  {/if}

  <div class="divider"></div>

  <!-- Background Pattern -->
  <div class="tool-group relative">
    <button
      class="tool-btn"
      class:active={showBgMenu || bgConfig?.type !== 'none'}
      title="Background Pattern"
      on:click={() => (showBgMenu = !showBgMenu)}
    >
      <Grid size={16} />
    </button>
    {#if showBgMenu}
      <div class="bg-menu-dropdown absolute top-[calc(100%+8px)] right-0 bg-neutral-900 border border-neutral-800 rounded shadow-lg p-1 z-50 flex flex-col min-w-[120px]">
        {#each bgPatterns as p}
          <button
            class="bg-pattern-btn text-left px-3 py-1.5 text-sm rounded hover:bg-neutral-800 text-neutral-300 hover:text-white flex items-center gap-2"
            class:bg-neutral-800={bgConfig?.type === p.id}
            class:text-white={bgConfig?.type === p.id}
            on:click={() => setBgPattern(p.id)}
          >
            {p.label}
          </button>
        {/each}
        {#if bgConfig?.type !== 'none'}
          <div class="border-t border-neutral-800 my-1"></div>
          <div class="px-2 py-1 flex items-center gap-2">
            <span class="text-xs text-neutral-400">Size</span>
            <input 
              type="range" 
              min="10" 
              max="100" 
              bind:value={bgConfig.spacing} 
              class="size-slider flex-1"
            />
          </div>
        {/if}
      </div>
      <!-- Invisible backdrop to close menu -->
      <div class="fixed inset-0 z-40" on:click={() => showBgMenu = false}></div>
    {/if}
  </div>

  <div class="divider"></div>

  <!-- Undo / Redo -->
  <div class="tool-group">
    <button
      class="tool-btn"
      disabled={!canUndo}
      title="Undo (Ctrl+Z)"
      on:click={() => dispatch('action', 'undo')}
    >
      <Undo2 size={16} />
    </button>
    <button
      class="tool-btn"
      disabled={!canRedo}
      title="Redo (Ctrl+Shift+Z)"
      on:click={() => dispatch('action', 'redo')}
    >
      <Redo2 size={16} />
    </button>
  </div>

  <div class="flex-spacer"></div>
</div>

<style>
  .canvas-toolbar {
    height: 48px;
    min-height: 48px;
    background: #171717;
    border-bottom: 1px solid #262626;
    display: flex;
    align-items: center;
    padding: 0 12px;
    gap: 4px;
    z-index: 50;
    flex-shrink: 0;
  }

  .tool-group {
    display: flex;
    align-items: center;
    gap: 2px;
  }

  .divider {
    width: 1px;
    height: 20px;
    background: #262626;
    margin: 0 6px;
    flex-shrink: 0;
  }

  .flex-spacer {
    flex-grow: 1;
  }

  /* ── Tool buttons ────────────────────────────────────────────── */

  .tool-btn {
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: none;
    border-radius: 6px;
    background: transparent;
    color: #a3a3a3;
    cursor: pointer;
    transition: all 0.15s ease;
    padding: 0;
  }

  .tool-btn:hover:not(:disabled) {
    background: #262626;
    color: #f5f5f5;
  }

  .tool-btn.active {
    background: #262626;
    color: #f5f5f5;
    box-shadow: inset 0 0 0 1px #404040;
  }

  .tool-btn:disabled {
    color: #404040;
    cursor: not-allowed;
  }

  /* ── Color swatches ──────────────────────────────────────────── */

  .color-swatch {
    width: 20px;
    height: 20px;
    border-radius: 50%;
    border: 2px solid transparent;
    background: var(--swatch-color);
    padding: 0;
    cursor: pointer;
    transition: border-color 0.15s ease, transform 0.1s ease;
    flex-shrink: 0;
  }

  .color-swatch:hover {
    transform: scale(1.15);
  }

  .color-swatch.active {
    border-color: #f5f5f5;
  }

  .picker-wrapper {
    width: 20px;
    height: 20px;
    position: relative;
    flex-shrink: 0;
  }

  .color-input {
    width: 20px;
    height: 20px;
    border: none;
    border-radius: 4px;
    padding: 0;
    cursor: pointer;
    background: transparent;
  }

  .color-input::-webkit-color-swatch-wrapper {
    padding: 0;
  }

  .color-input::-webkit-color-swatch {
    border: 1px solid #404040;
    border-radius: 4px;
  }

  /* ── Size slider ─────────────────────────────────────────────── */

  .size-group {
    gap: 8px;
  }

  .size-label {
    font-size: 11px;
    color: #737373;
    min-width: 30px;
    text-align: right;
    font-family: 'Inter', system-ui, sans-serif;
    user-select: none;
  }

  .size-slider {
    width: 80px;
    height: 4px;
    accent-color: #a3a3a3;
    cursor: pointer;
  }

  /* ── Text tools ──────────────────────────────────────────────── */
  .text-config-group {
    gap: 4px;
  }

  .font-select {
    background: #262626;
    color: #f5f5f5;
    border: 1px solid #404040;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 11px;
    outline: none;
    cursor: pointer;
  }

  .text-style-btn {
    width: 24px;
    height: 24px;
    border-radius: 4px;
  }

  .size-number-input {
    width: 50px;
    background: #262626;
    color: #f5f5f5;
    border: 1px solid #404040;
    border-radius: 4px;
    padding: 2px 4px;
    font-size: 12px;
    outline: none;
    text-align: right;
  }
</style>
