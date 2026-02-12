<script lang="ts">
    import { Plus } from "lucide-svelte";

    let {
        onadd,
    }: {
        onadd?: () => void;
    } = $props();
</script>

<button class="ghost-block" onclick={onadd} title="Add a new block">
    <div class="ghost-content">
        <Plus size={16} strokeWidth={1.5} />
        <span>Add a block</span>
    </div>
</button>

<style>
    .ghost-block {
        width: 100%;
        min-height: 64px;
        border: 1.5px dashed #404040;
        border-radius: 8px;
        background: transparent;
        cursor: pointer;
        transition: all 0.2s ease;
        display: flex;
        align-items: center;
        justify-content: center;
        margin-top: 12px;
    }

    .ghost-block:hover {
        border-color: #737373;
        background: rgba(64, 64, 64, 0.15);
    }

    .ghost-block:hover .ghost-content {
        color: #a3a3a3;
    }

    .ghost-content {
        display: flex;
        align-items: center;
        gap: 8px;
        color: #525252;
        font-size: 0.8rem;
        transition: color 0.2s ease;
    }
</style>
