<script lang="ts">
    /**
     * SettingsModal.svelte
     * ====================
     * Full-screen overlay settings panel accessible from NavRail.
     * Sections: General, AI & RAG, About.
     */
    import { onMount } from "svelte";
    import {
        X,
        FolderOpen,
        Key,
        Brain,
        Info,
        Save,
        Eye,
        EyeOff,
        Loader2,
        CheckCircle,
        Database,
        Network,
        Cpu,
    } from "lucide-svelte";
    import { isSettingsOpen, closeSettings } from "$lib/stores/settingsStore";
    import { getSettings, saveSettings } from "$lib/client/apiClient";
    import { addToast } from "$lib/stores/toastStore";
    import type { AppSettings } from "$lib/client/_apiTypes";
    import { open } from "@tauri-apps/plugin-dialog";

    // ── State ────────────────────────────────────────────────────────────

    let loading = $state(true);
    let saving = $state(false);
    let activeTab = $state<"general" | "ai" | "about">("general");

    // Settings fields (editable copies)
    let vaultPath = $state("");
    let apiKey = $state("");
    let apiKeySet = $state(false);
    let showApiKey = $state(false);
    let embeddingModel = $state("");
    let llmModel = $state("");
    let autoSaveDelay = $state(2.5);

    // RAG status (read-only)
    let ragEnabled = $state(false);
    let faissVectors = $state(0);
    let graphNodes = $state(0);
    let graphEdges = $state(0);

    // Track if user changed the API key field or Vault Path
    let apiKeyDirty = $state(false);
    let vaultPathDirty = $state(false);

    // ── Lifecycle ────────────────────────────────────────────────────────

    $effect(() => {
        if ($isSettingsOpen) {
            loadSettings();
        }
    });

    async function loadSettings() {
        loading = true;
        try {
            const s: AppSettings = await getSettings();
            vaultPath = s.vaultPath;
            apiKey = s.googleApiKey;
            apiKeySet = s.googleApiKeySet;
            embeddingModel = s.embeddingModel;
            llmModel = s.llmModel;
            autoSaveDelay = s.autoSaveDelay;
            ragEnabled = s.ragEnabled;
            faissVectors = s.faissVectors;
            graphNodes = s.graphNodes;
            graphEdges = s.graphEdges;
            apiKeyDirty = false;
            vaultPathDirty = false;
            showApiKey = false;
        } catch (err) {
            console.error("Failed to load settings:", err);
            addToast("error", "Failed to load settings");
        } finally {
            loading = false;
        }
    }

    async function handleSave() {
        saving = true;
        try {
            const payload: Record<string, unknown> = {};

            // Only send API key if user actually changed it
            if (apiKeyDirty) {
                payload.googleApiKey = apiKey;
            }

            if (vaultPathDirty) {
                payload.vaultPath = vaultPath;
            }

            payload.embeddingModel = embeddingModel;
            payload.llmModel = llmModel;
            payload.autoSaveDelay = autoSaveDelay;

            const result = await saveSettings(payload as any);

            if (result.success) {
                if (result.restartRequired) {
                    addToast("warning", "Settings saved. Restart the app to apply changes.", 5000);
                } else {
                    addToast("success", "Settings saved.");
                }
                closeSettings();
            } else {
                addToast("error", result.message || "Failed to save settings");
            }
        } catch (err) {
            console.error("Failed to save settings:", err);
            addToast("error", "Failed to save settings");
        } finally {
            saving = false;
        }
    }

    function handleKeydown(e: KeyboardEvent) {
        if (e.key === "Escape") {
            e.preventDefault();
            closeSettings();
        }
    }

    function handleBackdropClick(e: MouseEvent) {
        if ((e.target as HTMLElement).classList.contains("settings-overlay")) {
            closeSettings();
        }
    }

    function handleApiKeyInput() {
        apiKeyDirty = true;
    }

    async function handleBrowse() {
        try {
            const selected = await open({
                directory: true,
                multiple: false,
                title: "Select Vault Folder"
            });
            if (selected) {
                vaultPath = selected as string;
                vaultPathDirty = true;
            }
        } catch (err) {
            console.error("Failed to open dialog", err);
        }
    }

    const tabs = [
        { id: "general" as const, label: "General", icon: FolderOpen },
        { id: "ai" as const, label: "AI & RAG", icon: Brain },
        { id: "about" as const, label: "About", icon: Info },
    ];
</script>

{#if $isSettingsOpen}
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <div
        class="settings-overlay"
        role="dialog"
        aria-label="Settings"
        tabindex="-1"
        onkeydown={handleKeydown}
        onclick={handleBackdropClick}
    >
        <div class="settings-panel">
            <!-- Header -->
            <div class="settings-header">
                <h2>Settings</h2>
                <button class="close-btn" onclick={closeSettings} title="Close">
                    <X size={20} />
                </button>
            </div>

            <!-- Tab Navigation -->
            <div class="tab-bar">
                {#each tabs as tab}
                    <button
                        class="tab-btn"
                        class:active={activeTab === tab.id}
                        onclick={() => (activeTab = tab.id)}
                    >
                        {#if tab.icon === FolderOpen}
                            <FolderOpen size={16} />
                        {:else if tab.icon === Brain}
                            <Brain size={16} />
                        {:else}
                            <Info size={16} />
                        {/if}
                        <span>{tab.label}</span>
                    </button>
                {/each}
            </div>

            <!-- Content -->
            <div class="settings-content">
                {#if loading}
                    <div class="loading-state">
                        <Loader2 size={28} class="spin" />
                        <span>Loading settings…</span>
                    </div>
                {:else if activeTab === "general"}
                    <!-- ── General Tab ────────────────────────────── -->
                    <div class="settings-section">
                        <div class="section-header">
                            <FolderOpen size={18} />
                            <h3>Vault</h3>
                        </div>
                        <div class="field-group">
                            <span class="field-label">Vault Path</span>
                            <div style="display: flex; gap: 8px;">
                                <div class="field-readonly" style="flex: 1;">
                                    <FolderOpen size={14} />
                                    <span>{vaultPath}</span>
                                </div>
                                <button class="btn btn-secondary" onclick={handleBrowse}>
                                    Browse...
                                </button>
                            </div>
                            <p class="field-hint">
                                Requires restart to change.
                            </p>
                        </div>
                    </div>

                    <div class="settings-section">
                        <div class="section-header">
                            <Save size={18} />
                            <h3>Editor</h3>
                        </div>
                        <div class="field-group">
                            <label class="field-label" for="auto-save-delay">Auto-Save Delay</label>
                            <div class="slider-group">
                                <input
                                    id="auto-save-delay"
                                    type="range"
                                    min="0.5"
                                    max="10"
                                    step="0.5"
                                    bind:value={autoSaveDelay}
                                    class="slider"
                                />
                                <span class="slider-value">{autoSaveDelay}s</span>
                            </div>
                            <p class="field-hint">
                                How long to wait after the last keystroke before auto-saving.
                            </p>
                        </div>
                    </div>

                {:else if activeTab === "ai"}
                    <!-- ── AI & RAG Tab ───────────────────────────── -->
                    <div class="settings-section">
                        <div class="section-header">
                            <Key size={18} />
                            <h3>Google API Key</h3>
                            {#if apiKeySet}
                                <span class="status-badge success">
                                    <CheckCircle size={12} />
                                    Configured
                                </span>
                            {:else}
                                <span class="status-badge warning">Not set</span>
                            {/if}
                        </div>
                        <div class="field-group">
                            <label class="field-label" for="api-key">API Key</label>
                            <div class="input-with-toggle">
                                {#if showApiKey}
                                    <input
                                        id="api-key"
                                        type="text"
                                        bind:value={apiKey}
                                        oninput={handleApiKeyInput}
                                        placeholder="Enter your Google API key..."
                                        class="text-input"
                                        spellcheck="false"
                                    />
                                {:else}
                                    <input
                                        id="api-key"
                                        type="password"
                                        bind:value={apiKey}
                                        oninput={handleApiKeyInput}
                                        placeholder="Enter your Google API key..."
                                        class="text-input"
                                        spellcheck="false"
                                    />
                                {/if}
                                <button
                                    class="toggle-visibility"
                                    onclick={() => (showApiKey = !showApiKey)}
                                    title={showApiKey ? "Hide" : "Show"}
                                >
                                    {#if showApiKey}
                                        <EyeOff size={16} />
                                    {:else}
                                        <Eye size={16} />
                                    {/if}
                                </button>
                            </div>
                            <p class="field-hint">
                                Used for embeddings, semantic search, reranking, and LLM synthesis.
                                Saved to <code>google_api_key.json</code>. Requires restart to apply.
                            </p>
                        </div>
                    </div>

                    <div class="settings-section">
                        <div class="section-header">
                            <Cpu size={18} />
                            <h3>Models</h3>
                        </div>
                        <div class="field-group">
                            <label class="field-label" for="embedding-model">Embedding Model</label>
                            <input
                                id="embedding-model"
                                type="text"
                                bind:value={embeddingModel}
                                class="text-input"
                                spellcheck="false"
                            />
                        </div>
                        <div class="field-group">
                            <label class="field-label" for="llm-model">LLM Model</label>
                            <input
                                id="llm-model"
                                type="text"
                                bind:value={llmModel}
                                class="text-input"
                                spellcheck="false"
                            />
                        </div>
                        <p class="field-hint">
                            Changes to models require a full re-index after restart.
                        </p>
                    </div>

                {:else if activeTab === "about"}
                    <!-- ── About Tab ──────────────────────────────── -->
                    <div class="settings-section">
                        <div class="section-header">
                            <Info size={18} />
                            <h3>Sushi Notes</h3>
                        </div>
                        <div class="about-info">
                            <div class="about-logo">
                                <img src="/logo2.png" alt="Sushi" />
                            </div>
                            <p class="about-tagline">A beautiful, AI-powered note-taking app</p>
                        </div>
                    </div>

                    <div class="settings-section">
                        <div class="section-header">
                            <Database size={18} />
                            <h3>RAG Status</h3>
                            {#if ragEnabled}
                                <span class="status-badge success">
                                    <CheckCircle size={12} />
                                    Active
                                </span>
                            {:else}
                                <span class="status-badge warning">Disabled</span>
                            {/if}
                        </div>
                        <div class="stats-grid">
                            <div class="stat-card">
                                <Database size={20} />
                                <div class="stat-value">{faissVectors.toLocaleString()}</div>
                                <div class="stat-label">Vectors</div>
                            </div>
                            <div class="stat-card">
                                <Cpu size={20} />
                                <div class="stat-value">{graphNodes.toLocaleString()}</div>
                                <div class="stat-label">Graph Nodes</div>
                            </div>
                            <div class="stat-card">
                                <Network size={20} />
                                <div class="stat-value">{graphEdges.toLocaleString()}</div>
                                <div class="stat-label">Graph Edges</div>
                            </div>
                        </div>
                    </div>
                {/if}
            </div>

            <!-- Footer -->
            {#if activeTab !== "about"}
                <div class="settings-footer">
                    <button class="btn btn-secondary" onclick={closeSettings}>
                        Cancel
                    </button>
                    <button class="btn btn-primary" onclick={handleSave} disabled={saving}>
                        {#if saving}
                            <Loader2 size={16} class="spin" />
                            Saving…
                        {:else}
                            <Save size={16} />
                            Save Changes
                        {/if}
                    </button>
                </div>
            {/if}
        </div>
    </div>
{/if}

<style>
    /* ── Overlay ──────────────────────────────────────────────── */
    .settings-overlay {
        position: fixed;
        inset: 0;
        z-index: 9999;
        display: flex;
        align-items: center;
        justify-content: center;
        background: rgba(0, 0, 0, 0.6);
        backdrop-filter: blur(8px);
        animation: fadeIn 0.15s ease-out;
    }

    @keyframes fadeIn {
        from { opacity: 0; }
        to { opacity: 1; }
    }

    /* ── Panel ────────────────────────────────────────────────── */
    .settings-panel {
        width: min(620px, 92vw);
        max-height: 85vh;
        display: flex;
        flex-direction: column;
        background: rgba(23, 23, 23, 0.95);
        border: 1px solid rgba(63, 63, 70, 0.5);
        border-radius: 16px;
        box-shadow:
            0 25px 50px rgba(0, 0, 0, 0.5),
            0 0 0 1px rgba(255, 255, 255, 0.03);
        animation: slideUp 0.2s ease-out;
        overflow: hidden;
    }

    @keyframes slideUp {
        from { transform: translateY(12px); opacity: 0; }
        to { transform: translateY(0); opacity: 1; }
    }

    /* ── Header ───────────────────────────────────────────────── */
    .settings-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 20px 24px 0;
    }

    .settings-header h2 {
        font-size: 1.25rem;
        font-weight: 600;
        color: #f4f4f5;
        margin: 0;
        letter-spacing: -0.01em;
    }

    .close-btn {
        width: 32px;
        height: 32px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: transparent;
        border: none;
        border-radius: 8px;
        color: #71717a;
        cursor: pointer;
        transition: all 0.15s;
    }
    .close-btn:hover {
        background: rgba(63, 63, 70, 0.5);
        color: #f4f4f5;
    }

    /* ── Tabs ─────────────────────────────────────────────────── */
    .tab-bar {
        display: flex;
        gap: 2px;
        padding: 16px 24px 0;
        border-bottom: 1px solid rgba(63, 63, 70, 0.3);
    }

    .tab-btn {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 8px 16px 12px;
        background: transparent;
        border: none;
        border-bottom: 2px solid transparent;
        color: #a1a1aa;
        font-size: 0.85rem;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.15s;
        font-family: inherit;
    }
    .tab-btn:hover {
        color: #d4d4d8;
    }
    .tab-btn.active {
        color: #c084fc;
        border-bottom-color: #c084fc;
    }

    /* ── Content ──────────────────────────────────────────────── */
    .settings-content {
        flex: 1;
        overflow-y: auto;
        padding: 20px 24px;
        scrollbar-width: thin;
        scrollbar-color: rgba(82, 82, 91, 0.5) transparent;
    }

    .loading-state {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 12px;
        padding: 48px 0;
        color: #71717a;
        font-size: 0.9rem;
    }

    /* ── Sections ─────────────────────────────────────────────── */
    .settings-section {
        margin-bottom: 24px;
    }
    .settings-section:last-child {
        margin-bottom: 0;
    }

    .section-header {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 14px;
        color: #d4d4d8;
    }
    .section-header h3 {
        font-size: 0.95rem;
        font-weight: 600;
        margin: 0;
    }

    .status-badge {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.7rem;
        font-weight: 500;
        margin-left: auto;
    }
    .status-badge.success {
        background: rgba(34, 197, 94, 0.12);
        color: #4ade80;
        border: 1px solid rgba(34, 197, 94, 0.2);
    }
    .status-badge.warning {
        background: rgba(234, 179, 8, 0.12);
        color: #facc15;
        border: 1px solid rgba(234, 179, 8, 0.2);
    }

    /* ── Fields ───────────────────────────────────────────────── */
    .field-group {
        margin-bottom: 16px;
    }
    .field-group:last-child {
        margin-bottom: 0;
    }

    .field-label {
        display: block;
        font-size: 0.8rem;
        font-weight: 500;
        color: #a1a1aa;
        margin-bottom: 6px;
    }

    .field-readonly {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 10px 14px;
        background: rgba(39, 39, 42, 0.6);
        border: 1px solid rgba(63, 63, 70, 0.3);
        border-radius: 10px;
        color: #d4d4d8;
        font-size: 0.85rem;
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        word-break: break-all;
    }

    .field-hint {
        margin: 6px 0 0;
        font-size: 0.75rem;
        color: #71717a;
        line-height: 1.4;
    }
    .field-hint code {
        padding: 1px 5px;
        background: rgba(63, 63, 70, 0.4);
        border-radius: 4px;
        font-size: 0.72rem;
        color: #a1a1aa;
    }

    .text-input {
        width: 100%;
        padding: 10px 14px;
        background: rgba(39, 39, 42, 0.6);
        border: 1px solid rgba(63, 63, 70, 0.4);
        border-radius: 10px;
        color: #f4f4f5;
        font-size: 0.85rem;
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        outline: none;
        transition: border-color 0.15s;
        box-sizing: border-box;
    }
    .text-input:focus {
        border-color: rgba(168, 85, 247, 0.5);
        box-shadow: 0 0 0 2px rgba(168, 85, 247, 0.08);
    }
    .text-input::placeholder {
        color: #52525b;
    }

    .input-with-toggle {
        position: relative;
        display: flex;
        align-items: center;
    }
    .input-with-toggle .text-input {
        padding-right: 42px;
    }
    .toggle-visibility {
        position: absolute;
        right: 8px;
        width: 30px;
        height: 30px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: transparent;
        border: none;
        border-radius: 6px;
        color: #71717a;
        cursor: pointer;
        transition: all 0.15s;
    }
    .toggle-visibility:hover {
        color: #d4d4d8;
        background: rgba(63, 63, 70, 0.4);
    }

    /* ── Slider ───────────────────────────────────────────────── */
    .slider-group {
        display: flex;
        align-items: center;
        gap: 14px;
    }

    .slider {
        flex: 1;
        height: 6px;
        -webkit-appearance: none;
        appearance: none;
        background: rgba(63, 63, 70, 0.5);
        border-radius: 3px;
        outline: none;
    }
    .slider::-webkit-slider-thumb {
        -webkit-appearance: none;
        width: 18px;
        height: 18px;
        background: #c084fc;
        border-radius: 50%;
        cursor: pointer;
        border: 2px solid rgba(23, 23, 23, 0.8);
        box-shadow: 0 2px 6px rgba(168, 85, 247, 0.3);
        transition: transform 0.15s;
    }
    .slider::-webkit-slider-thumb:hover {
        transform: scale(1.15);
    }

    .slider-value {
        font-size: 0.85rem;
        font-weight: 600;
        color: #c084fc;
        min-width: 36px;
        text-align: right;
        font-variant-numeric: tabular-nums;
    }

    /* ── About ────────────────────────────────────────────────── */
    .about-info {
        display: flex;
        flex-direction: column;
        align-items: center;
        padding: 20px 0;
    }
    .about-logo {
        width: 64px;
        height: 64px;
        margin-bottom: 12px;
    }
    .about-logo img {
        width: 100%;
        height: 100%;
        object-fit: contain;
    }
    .about-tagline {
        font-size: 0.9rem;
        color: #a1a1aa;
        margin: 0;
    }

    /* ── Stats Grid ───────────────────────────────────────────── */
    .stats-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 12px;
    }

    .stat-card {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 6px;
        padding: 16px 12px;
        background: rgba(39, 39, 42, 0.5);
        border: 1px solid rgba(63, 63, 70, 0.3);
        border-radius: 12px;
        color: #a1a1aa;
    }
    .stat-value {
        font-size: 1.3rem;
        font-weight: 700;
        color: #f4f4f5;
        font-variant-numeric: tabular-nums;
    }
    .stat-label {
        font-size: 0.72rem;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #71717a;
    }

    /* ── Footer ───────────────────────────────────────────────── */
    .settings-footer {
        display: flex;
        justify-content: flex-end;
        gap: 10px;
        padding: 16px 24px;
        border-top: 1px solid rgba(63, 63, 70, 0.3);
    }

    .btn {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 8px 18px;
        border-radius: 10px;
        font-size: 0.85rem;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.15s;
        border: none;
        font-family: inherit;
    }
    .btn:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }

    .btn-secondary {
        background: rgba(63, 63, 70, 0.4);
        color: #a1a1aa;
        border: 1px solid rgba(63, 63, 70, 0.4);
    }
    .btn-secondary:hover:not(:disabled) {
        background: rgba(63, 63, 70, 0.6);
        color: #d4d4d8;
    }

    .btn-primary {
        background: rgba(168, 85, 247, 0.15);
        color: #c084fc;
        border: 1px solid rgba(168, 85, 247, 0.3);
    }
    .btn-primary:hover:not(:disabled) {
        background: rgba(168, 85, 247, 0.25);
        border-color: rgba(168, 85, 247, 0.5);
    }

    /* ── Spin animation ──────────────────────────────────────── */
    :global(.spin) {
        animation: spin 1s linear infinite;
    }
    @keyframes spin {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
    }
</style>
