<script lang="ts">
    let { visible = true } = $props();
</script>

{#if visible}
    <div class="splash-overlay" class:fade-out={!visible}>
        <div class="splash-content">
            <div class="logo-container">
                <img src="/logo2.png" alt="Sushi" class="splash-logo" />
            </div>
            <h1 class="app-name">Sushi</h1>
            <p class="app-tagline">Your notes, your way</p>
            <div class="loading-bar">
                <div class="loading-bar-fill"></div>
            </div>
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

    .logo-container {
        animation: float 2s ease-in-out infinite;
    }

    .splash-logo {
        width: 120px;
        height: 120px;
        object-fit: contain;
        filter: drop-shadow(0 0 30px rgba(251, 146, 60, 0.3));
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

    .loading-bar {
        width: 160px;
        height: 3px;
        background: #262626;
        border-radius: 2px;
        overflow: hidden;
        margin-top: 1.5rem;
    }

    .loading-bar-fill {
        height: 100%;
        width: 40%;
        background: linear-gradient(90deg, #fb923c, #f97316);
        border-radius: 2px;
        animation: loading 1.2s ease-in-out infinite;
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

    @keyframes loading {
        0% {
            transform: translateX(-100%);
        }
        50% {
            transform: translateX(200%);
        }
        100% {
            transform: translateX(400%);
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
