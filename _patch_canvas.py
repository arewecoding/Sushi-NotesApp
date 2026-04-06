import sys

f = r'c:\Users\ADMIN\Development\PyTauri\test project\test_1\sushi\src\lib\components\editor\CanvasBlock.svelte'
with open(f, 'r', encoding='utf-8') as fh:
    content = fh.read()

old1 = """    type BlockState = 'thumbnail' | 'loading' | 'active';
    let blockState = $state<BlockState>('thumbnail');"""

new1 = """    type BlockState = 'thumbnail' | 'loading' | 'active' | 'regenerating';
    let blockState = $state<BlockState>('thumbnail');

    async function regenerateThumbnail(canvasData: any, lastViewport: any) {
        if (!canvasRef || !$activeNoteId) return;
        
        blockState = 'regenerating';
        await tick();
        await tick();

        if (canvasComponent) {
            canvasComponent.deserialize(JSON.stringify(canvasData));
            // Let the canvas render the strokes
            await new Promise(r => requestAnimationFrame(r));
            await new Promise(r => requestAnimationFrame(r));
            
            const dataUrl = await canvasComponent.generateThumbnail();
            
            await canvasInvoke('save_canvas_block_cmd', {
                noteId: $activeNoteId,
                blockId,
                canvasRef,
                canvasData: canvasData,
                thumbnailDataUrl: dataUrl
            });
            
            // Re-trigger load
            const tRef = initialData.thumbnail_ref;
            if (tRef) {
                getResourcePath($activeNoteId, tRef, blockId, initialData).then(result => {
                    if (typeof result === 'string') {
                        thumbnailSrc = `${convertFileSrc(result)}?t=${Date.now()}`;
                    }
                });
            }
            
            canvasComponent.clearEngine();
        }
        
        blockState = 'thumbnail';
    }"""

old2 = """    $effect(() => {
        if (thumbnailRef) {
            const noteId = $activeNoteId;
            if (noteId) {
                getResourcePath(noteId, thumbnailRef).then(absPath => {
                    if (absPath) {
                        // Append cache-buster so the browser reloads the updated thumbnail image after a save
                        thumbnailSrc = `${convertFileSrc(absPath)}?t=${Date.now()}`;
                    }
                });
            }
        }
    });"""

new2 = """    $effect(() => {
        if (thumbnailRef) {
            const noteId = $activeNoteId;
            if (noteId) {
                getResourcePath(noteId, thumbnailRef, blockId, initialData).then(result => {
                    if (typeof result === 'string') {
                        // Append cache-buster so the browser reloads the updated thumbnail image after a save
                        thumbnailSrc = `${convertFileSrc(result)}?t=${Date.now()}`;
                    } else if (result?.status === 'regeneration_required') {
                        regenerateThumbnail(result.canvasData, result.lastViewport);
                    }
                });
            }
        } else {
            // Null thumbnailRef means static placeholder
            thumbnailSrc = null;
        }
    });"""

old3 = """    {:else if blockState === 'active'}
        <div class="canvas-active-shell">"""

new3 = """    {:else if blockState === 'active' || blockState === 'regenerating'}
        <!-- When regenerating, keep it in DOM but hidden so Canvas computes correctly -->
        <div class="canvas-active-shell" style={blockState === 'regenerating' ? 'position: absolute; opacity: 0; pointer-events: none; z-index: -100;' : ''}>"""

for o, n in [(old1, new1), (old2, new2), (old3, new3)]:
    oc = o.replace('\n', '\r\n')
    nc = n.replace('\n', '\r\n')
    if oc in content:
        content = content.replace(oc, nc, 1)
    elif o in content:
        content = content.replace(o, n, 1)
    else:
        print('ERROR: could not find chunk:')
        print(o[:40])
        sys.exit(1)

with open(f, 'w', encoding='utf-8') as fh:
    fh.write(content)
print('OK')
