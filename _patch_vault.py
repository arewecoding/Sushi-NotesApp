import sys

f = r'c:\Users\ADMIN\Development\PyTauri\test project\test_1\sushi\src-tauri\src-python\sushi\vault_service.py'
with open(f, 'r', encoding='utf-8') as fh:
    content = fh.read()

old = '''    def save_canvas_block(
        self,
        note_id: str,
        block_id: str,
        canvas_ref: str,
        canvas_data: dict,
        thumbnail_data_url: Optional[str] = None,
    ) -> str:
        """Persist an embedded canvas block and its thumbnail inside the note's resources dir.
        
        If thumbnail_data_url is omitted, the prior thumbnail on disk (if any) is preserved.

        Args:
            note_id: The owning note's UUID.
            block_id: The block's UUID within the note.
            canvas_ref: Filename of the canvas file, e.g. ``abc123.jcanvas``.
            canvas_data: Serialized canvas state from the WASM engine.
            thumbnail_data_url: Optional base64 PNG data URL to save as the thumbnail.

        Returns:
            The thumbnail filename (stem + "-thumb.png").

        Raises:
            FileNotFoundError: If the note's path cannot be resolved from the DB.
        """
        note_path = get_note_filepath(self.db, note_id)
        if not note_path:
            raise FileNotFoundError(f"Note path not found for note_id={note_id}")

        res_id = Path(canvas_ref).stem
        self.resource_manager.update_resource(res_id, canvas_data)

        # Write thumbnail PNG via filesys helper (only if provided)
        thumb_filename = f"{res_id}-thumb.png"
        
        if thumbnail_data_url:
            self.resource_manager.update_resource(res_id + "-thumb", thumbnail_data_url)'''

new = '''    def save_canvas_block(
        self,
        note_id: str,
        block_id: str,
        canvas_ref: str,
        canvas_data: dict,
        thumbnail_data_url: Optional[str] = None,
    ) -> Optional[str]:
        """Persist an embedded canvas block and its thumbnail inside the note's resources dir.
        
        If thumbnail_data_url is omitted, the prior thumbnail on disk (if any) is preserved.

        Args:
            note_id: The owning note's UUID.
            block_id: The block's UUID within the note.
            canvas_ref: Filename of the canvas file, e.g. ``abc123.jcanvas``.
            canvas_data: Serialized canvas state from the WASM engine.
            thumbnail_data_url: Optional base64 PNG data URL to save as the thumbnail.

        Returns:
            The thumbnail filename (stem + "-thumb.png").

        Raises:
            FileNotFoundError: If the note's path cannot be resolved from the DB.
        """
        note_path = get_note_filepath(self.db, note_id)
        if not note_path:
            raise FileNotFoundError(f"Note path not found for note_id={note_id}")

        res_id = Path(canvas_ref).stem
        self.resource_manager.update_resource(res_id, canvas_data)

        thumb_filename = None
        if thumbnail_data_url:
            try:
                from sushi.resource_manager import ResourceNotFound
                thumb_res = self.resource_manager.get_resource(res_id + "-thumb", check_exists=False)
            except ResourceNotFound:
                thumb_res = self.resource_manager.create_resource(block_id, "thumbnail", note_path.parent, res_id=res_id)
            
            self.resource_manager.update_resource(thumb_res.resource_id, thumbnail_data_url)
            thumb_filename = thumb_res.file_path.name'''

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
