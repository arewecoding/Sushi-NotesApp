<script lang="ts">
    import { onMount } from "svelte";

    interface MenuItem {
        label: string;
        icon?: string;
        action: () => void;
        danger?: boolean;
    }

    let {
        x = 0,
        y = 0,
        items = [],
        onclose,
    }: {
        x?: number;
        y?: number;
        items?: MenuItem[];
        onclose?: () => void;
    } = $props();

    let menuEl: HTMLDivElement | undefined = $state();

    onMount(() => {
        function handleClickOutside(e: MouseEvent) {
            if (menuEl && !menuEl.contains(e.target as Node)) {
                onclose?.();
            }
        }
        function handleEscape(e: KeyboardEvent) {
            if (e.key === "Escape") onclose?.();
        }
        // Delay to avoid the same click that opened the menu from closing it
        setTimeout(() => {
            document.addEventListener("mousedown", handleClickOutside);
            document.addEventListener("keydown", handleEscape);
        }, 0);
        return () => {
            document.removeEventListener("mousedown", handleClickOutside);
            document.removeEventListener("keydown", handleEscape);
        };
    });

    // Clamp position to viewport
    let clampedX = $derived(Math.min(x, window.innerWidth - 200));
    let clampedY = $derived(
        Math.min(y, window.innerHeight - items.length * 36 - 16),
    );
</script>

<div
    class="context-menu"
    style="left: {clampedX}px; top: {clampedY}px"
    bind:this={menuEl}
    role="menu"
>
    {#each items as item}
        <button
            class="context-item"
            class:danger={item.danger}
            onclick={() => {
                item.action();
                onclose?.();
            }}
            role="menuitem"
        >
            {#if item.icon}
                <span class="item-icon">{item.icon}</span>
            {/if}
            <span>{item.label}</span>
        </button>
    {/each}
</div>

<style>
    .context-menu {
        position: fixed;
        z-index: 9999;
        min-width: 160px;
        background: #1e1e1e;
        border: 1px solid #404040;
        border-radius: 8px;
        padding: 4px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
        animation: menu-in 0.1s ease-out;
    }

    .context-item {
        display: flex;
        align-items: center;
        gap: 8px;
        width: 100%;
        padding: 6px 12px;
        border: none;
        background: none;
        color: #d4d4d4;
        font-size: 0.8rem;
        border-radius: 5px;
        cursor: pointer;
        text-align: left;
        transition: background 0.1s ease;
    }

    .context-item:hover {
        background: #333333;
        color: #f5f5f5;
    }

    .context-item.danger:hover {
        background: rgba(239, 68, 68, 0.15);
        color: #ef4444;
    }

    .item-icon {
        width: 16px;
        text-align: center;
        font-size: 0.75rem;
    }

    @keyframes menu-in {
        from {
            opacity: 0;
            transform: scale(0.95);
        }
        to {
            opacity: 1;
            transform: scale(1);
        }
    }
</style>
