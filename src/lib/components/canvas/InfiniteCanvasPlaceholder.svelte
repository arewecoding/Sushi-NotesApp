<script lang="ts">
    let { canvasId, filePath }: { canvasId: string; filePath: string } = $props();
</script>

<div class="canvas-placeholder">
    <div class="icon-circle">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>
            <path d="m15 5 4 4"/>
        </svg>
    </div>
    <h2 class="title">Infinite Canvas</h2>
    <p class="file-path">{filePath}</p>
    <p class="phase-hint">
        Canvas engine integration coming in Phase 12.
    </p>
    <span class="id-badge">{canvasId}</span>
</div>

<style>
    .canvas-placeholder {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        height: 100%;
        gap: 0.75rem;
        color: var(--text-muted, #888);
        padding: 2rem;
    }

    .icon-circle {
        width: 72px;
        height: 72px;
        border-radius: 50%;
        background: rgba(249, 115, 22, 0.08);
        border: 1px solid rgba(249, 115, 22, 0.2);
        display: flex;
        align-items: center;
        justify-content: center;
        color: #f97316;
        margin-bottom: 0.5rem;
    }

    .title {
        font-size: 1.25rem;
        font-weight: 600;
        color: #d4d4d4;
        margin: 0;
    }

    .file-path {
        font-size: 0.8rem;
        color: #737373;
        font-family: monospace;
        max-width: 400px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        margin: 0;
    }

    .phase-hint {
        font-size: 0.85rem;
        opacity: 0.5;
        margin: 0;
    }

    .id-badge {
        font-size: 0.7rem;
        background: #262626;
        border: 1px solid #404040;
        border-radius: 4px;
        padding: 2px 8px;
        font-family: monospace;
        color: #737373;
        margin-top: 0.5rem;
    }
</style>
