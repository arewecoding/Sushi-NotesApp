<script lang="ts">
    let { bookId, filePath }: { bookId: string; filePath: string } = $props();
</script>

<div class="book-placeholder">
    <div class="icon-circle">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>
            <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
        </svg>
    </div>
    <h2 class="title">Notebook Canvas</h2>
    <p class="file-path">{filePath}</p>
    <p class="phase-hint">
        Notebook canvas integration coming in Phase 12.
    </p>
    <span class="id-badge">{bookId}</span>
</div>

<style>
    .book-placeholder {
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
        background: rgba(99, 102, 241, 0.08);
        border: 1px solid rgba(99, 102, 241, 0.2);
        display: flex;
        align-items: center;
        justify-content: center;
        color: #6366f1;
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
