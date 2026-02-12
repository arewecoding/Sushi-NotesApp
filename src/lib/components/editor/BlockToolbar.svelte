<script lang="ts">
    import {
        Trash2,
        ChevronUp,
        ChevronDown,
        MoreHorizontal,
    } from "lucide-svelte";

    let {
        visible = false,
        isFirst = false,
        isLast = false,
        ondelete,
        onmoveup,
        onmovedown,
    }: {
        visible?: boolean;
        isFirst?: boolean;
        isLast?: boolean;
        ondelete?: () => void;
        onmoveup?: () => void;
        onmovedown?: () => void;
    } = $props();
</script>

{#if visible}
    <div class="block-toolbar">
        <button
            class="toolbar-btn"
            onclick={onmoveup}
            disabled={isFirst}
            title="Move up"
        >
            <ChevronUp size={12} />
        </button>
        <button
            class="toolbar-btn"
            onclick={onmovedown}
            disabled={isLast}
            title="Move down"
        >
            <ChevronDown size={12} />
        </button>
        <div class="toolbar-sep"></div>
        <button
            class="toolbar-btn delete-btn"
            onclick={ondelete}
            title="Delete block"
        >
            <Trash2 size={11} />
        </button>
        <button class="toolbar-btn" title="More options">
            <MoreHorizontal size={12} />
        </button>
    </div>
{/if}

<style>
    .block-toolbar {
        position: absolute;
        top: -13px;
        right: 8px;
        z-index: 15;
        display: flex;
        align-items: center;
        gap: 1px;
        background: #262626;
        border: 1px solid #404040;
        border-radius: 6px;
        padding: 1px 3px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
        animation: toolbar-in 0.1s ease-out;
    }

    .toolbar-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 22px;
        height: 20px;
        border-radius: 4px;
        color: #737373;
        background: none;
        border: none;
        cursor: pointer;
        transition: all 0.1s ease;
    }

    .toolbar-btn:hover:not(:disabled) {
        background: #404040;
        color: #e5e5e5;
    }

    .toolbar-btn:disabled {
        opacity: 0.25;
        cursor: default;
    }

    .toolbar-btn.delete-btn:hover:not(:disabled) {
        background: rgba(239, 68, 68, 0.15);
        color: #ef4444;
    }

    .toolbar-sep {
        width: 1px;
        height: 12px;
        background: #404040;
        margin: 0 1px;
    }

    @keyframes toolbar-in {
        from {
            opacity: 0;
            transform: translateY(3px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
</style>
