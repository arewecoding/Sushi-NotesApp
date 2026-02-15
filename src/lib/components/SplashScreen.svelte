<script lang="ts">
    let { visible = true } = $props();
</script>

{#if visible}
    <div class="splash-overlay" class:fade-out={!visible}>
        <div class="splash-content">
            <div class="gif-container">
                <img
                    src="/loading_animation.gif"
                    alt="Loading"
                    class="splash-gif"
                />
            </div>
            <h1 class="app-name">Sushi</h1>
            <p class="app-tagline">Your notes, your way</p>
        </div>
    </div>
{/if}

<style>
    .splash-overlay {
        position: fixed;
        inset: 0;
        z-index: 9999;
        display: flex;
        align-items: center;
        justify-content: center;
        background: #171717;
        animation: fadeIn 0.2s ease-out;
        transition: opacity 0.5s ease-out;
    }

    .splash-overlay.fade-out {
        opacity: 0;
        pointer-events: none;
    }

    .splash-content {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 1rem;
    }

    .gif-container {
        animation: float 2s ease-in-out infinite;
    }

    .splash-gif {
        width: 300px;
        height: 300px;
        object-fit: contain;
        /* Feather/fade the edges to hide green screen lines */
        mask-image: radial-gradient(
            ellipse 80% 80% at center,
            black 50%,
            transparent 100%
        );
        -webkit-mask-image: radial-gradient(
            ellipse 80% 80% at center,
            black 50%,
            transparent 100%
        );
    }

    .app-name {
        font-size: 2rem;
        font-weight: 700;
        color: #f5f5f5;
        letter-spacing: 0.1em;
        margin: 0;
    }

    .app-tagline {
        font-size: 0.85rem;
        color: #737373;
        margin: 0;
        letter-spacing: 0.05em;
    }

    @keyframes float {
        0%,
        100% {
            transform: translateY(0px);
        }
        50% {
            transform: translateY(-8px);
        }
    }

    @keyframes fadeIn {
        from {
            opacity: 0;
        }
        to {
            opacity: 1;
        }
    }
</style>
