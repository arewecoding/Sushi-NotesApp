import sys

f = r'c:\Users\ADMIN\Development\PyTauri\test project\test_1\sushi\src-tauri\src-python\sushi\commands.py'
with open(f, 'r', encoding='utf-8') as fh:
    content = fh.read()

old = '''@commands.command()
async def get_resource_path_cmd(
    body: GetResourcePathRequest, app_handle: AppHandle
) -> dict:
    """Gets the absolute OS path for a resource file belonging to a note."""
    try:
        from sushi.filesys import get_note_filepath
        vault_service: VaultService = Manager.state(app_handle, VaultService)
        note_path = get_note_filepath(vault_service.db, body.note_id)
        if not note_path:
            return err(NOTE_NOT_FOUND, f"Note {body.note_id} not found")
        resource_path = note_path.parent / ".sushi-resources" / body.filename
        return ok({"path": str(resource_path)})
    except Exception as e:
        log.error("get_resource_path_failed", error=str(e), note_id=body.note_id)
        return err(NOTE_NOT_FOUND, str(e))'''

new = '''@commands.command()
async def get_resource_path_cmd(
    body: GetResourcePathRequest, app_handle: AppHandle
) -> dict:
    """Resolves the absolute OS path for a resource, with lazy integrity checks.

    Routes through ResourceManager.resolve_resource_path() so that missing files
    trigger recovery (canvas) or a regeneration_required signal (thumbnail).
    """
    try:
        from sushi.filesys import get_note_filepath
        vault_service: VaultService = Manager.state(app_handle, VaultService)
        note_path = get_note_filepath(vault_service.db, body.note_id)
        if not note_path:
            return err(NOTE_NOT_FOUND, f"Note {body.note_id} not found")

        result = vault_service.resource_manager.resolve_resource_path(
            filename=body.filename,
            note_dir=note_path.parent,
            block_id=body.block_id,
            block_data=body.block_data,
        )
        return ok(result)
    except Exception as e:
        log.error("get_resource_path_failed", error=str(e), note_id=body.note_id)
        return err(NOTE_NOT_FOUND, str(e))'''

# Try CRLF first
old_crlf = old.replace('\n', '\r\n')
new_crlf = new.replace('\n', '\r\n')
if old_crlf in content:
    content = content.replace(old_crlf, new_crlf, 1)
    with open(f, 'w', encoding='utf-8') as fh:
        fh.write(content)
    print('OK: replaced (CRLF)')
elif old in content:
    content = content.replace(old, new, 1)
    with open(f, 'w', encoding='utf-8') as fh:
        fh.write(content)
    print('OK: replaced')
else:
    print('ERROR: pattern not found')
    sys.exit(1)
