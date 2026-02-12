<script lang="ts">
    import { Plus } from "lucide-svelte";

    let {
        oninsert,
    }: {
        oninsert?: (type: string) => void;
    } = $props();

    let isHovered = $state(false);
    let showDropdown = $state(false);

    const blockTypes = [
        { type: "text", label: "Text", icon: "Aa" },
        { type: "code", label: "Code", icon: "</>" },
        { type: "todo", label: "Todo", icon: "☐" },
    ];

    function handleInsert(type: string) {
        showDropdown = false;
        isHovered = false;
        oninsert?.(type);
    }
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
    class="block-inserter"
    onmouseenter={() => (isHovered = true)}
    onmouseleave={() => {
        isHovered = false;
        showDropdown = false;
    }}
>
    <!-- The hover line -->
    <div class="inserter-line" class:visible={isHovered}>
        <div class="line-left"></div>
        <button
            class="inserter-button"
            onclick={() => (showDropdown = !showDropdown)}
            title="Add a block"
        >
            <Plus size={12} />
        </button>
        <div class="line-right"></div>
    </div>

    <!-- Block type dropdown -->
    {#if showDropdown}
        <div class="inserter-dropdown">
            {#each blockTypes as bt}
                <button
                    class="dropdown-item"
                    onclick={() => handleInsert(bt.type)}
                >
                    <span class="dropdown-icon">{bt.icon}</span>
                    <span>{bt.label}</span>
                </button>
            {/each}
        </div>
    {/if}
</div>

<style>
    .block-inserter {
        position: relative;
        height: 16px;
        display: flex;
        align-items: center;
        margin: -4px 0;
        z-index: 10;
    }

    .inserter-line {
        display: flex;
        align-items: center;
        width: 100%;
        opacity: 0;
        transition: opacity 0.15s ease;
    }

    .inserter-line.visible {
        opacity: 1;
    }

    .line-left,
    .line-right {
        flex: 1;
        height: 1px;
        background: #525252;
    }

    .inserter-button {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 20px;
        height: 20px;
        border-radius: 50%;
        background: #404040;
        color: #a3a3a3;
        border: 1px solid #525252;
        cursor: pointer;
        transition: all 0.15s ease;
        flex-shrink: 0;
        margin: 0 4px;
    }

    .inserter-button:hover {
        background: #f97316;
        color: white;
        border-color: #f97316;
        transform: scale(1.1);
    }

    .inserter-dropdown {
        position: absolute;
        top: 100%;
        left: 50%;
        transform: translateX(-50%);
        background: #262626;
        border: 1px solid #404040;
        border-radius: 8px;
        padding: 4px;
        display: flex;
        gap: 2px;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
        z-index: 20;
        animation: dropdown-in 0.1s ease-out;
    }

    .dropdown-item {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 6px 12px;
        border-radius: 6px;
        color: #d4d4d4;
        font-size: 0.75rem;
        cursor: pointer;
        transition: all 0.1s ease;
        white-space: nowrap;
        background: none;
        border: none;
    }

    .dropdown-item:hover {
        background: #404040;
        color: #f5f5f5;
    }

    .dropdown-icon {
        font-size: 0.7rem;
        color: #737373;
        font-family: monospace;
        width: 20px;
        text-align: center;
    }

    @keyframes dropdown-in {
        from {
            opacity: 0;
            transform: translateX(-50%) translateY(-4px);
        }
        to {
            opacity: 1;
            transform: translateX(-50%) translateY(0);
        }
    }
</style>
