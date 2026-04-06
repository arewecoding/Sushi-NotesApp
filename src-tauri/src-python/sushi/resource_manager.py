import os
import uuid
import json
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Type
from datetime import datetime, timezone
import structlog

from sushi.filesys import atomic_write, save_data_url_as_png

log = structlog.get_logger(__name__)

# ── Default viewport for regeneration payloads ────────────────────────────────
DEFAULT_VIEWPORT = {"offset_x": 0.0, "offset_y": 0.0, "scale": 1.0}


class ResourceNotFound(Exception):
    """Raised when a resource is not found in the DB."""
    pass


@dataclass
class Resource:
    resource_id: str
    resource_type: str
    file_path: Path
    block_id: str
    created_at: str

    def exists(self) -> bool:
        return self.file_path.exists()

    def regenerate(self, content_payload: Optional[Dict[str, Any]] = None):
        """Regenerate the file if missing."""
        raise NotImplementedError()

    def read(self) -> bytes:
        return self.file_path.read_bytes()


class CanvasResource(Resource):
    def regenerate(self, content_payload: Optional[Dict[str, Any]] = None):
        """Write a blank canvas JSON if missing."""
        log.info("regenerating_blank_canvas", block_id=self.block_id)
        default_canvas = {
            "version": "1",
            "size": {"width_mm": 210, "height_mm": 297, "preset": "A4"},
            "strokes": [],
            "texts": [],
            "images": []
        }
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(self.file_path, json.dumps(default_canvas))


class ThumbnailResource(Resource):
    def regenerate(self, content_payload: Optional[Dict[str, Any]] = None):
        """
        Backend cannot render thumbnails locally.
        This is a no-op — thumbnail regeneration is signalled to the frontend
        via resolve_resource_path returning a 'regeneration_required' payload.
        """
        pass


class ResourceManager:
    def __init__(self, db, vault_path: Path):
        self.db = db
        self.vault_path = Path(vault_path)
        self.last_indexed: Dict[str, str] = {}  # Map Note ID -> last_modified timestamp
        self._is_ready = False
        self._setup_db()

    def _wait_until_ready(self):
        if not self._is_ready:
            raise RuntimeError("ResourceManager is still initializing. Please wait for vault-ready.")

    def _setup_db(self):
        cursor = self.db.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS resources (
                resource_id TEXT PRIMARY KEY,
                resource_type TEXT NOT NULL,
                file_path TEXT NOT NULL,
                block_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        self.db.conn.commit()

    def _get_resource_class(self, resource_type: str) -> Type[Resource]:
        if resource_type == "canvas":
            return CanvasResource
        elif resource_type == "thumbnail":
            return ThumbnailResource
        return Resource

    # ══════════════════════════════════════════════════════════════════════════
    # CREATE — sole authority for resource file creation
    # ══════════════════════════════════════════════════════════════════════════

    def create_resource(self, block_id: str, resource_type: str, note_dir: Path, res_id: Optional[str] = None) -> Resource:
        """Generates UUID (or uses provided), writes blank file, inserts DB row, returns resource.
        
        This is the ONLY method that creates resource files on disk.
        Canvas: writes blank .jcanvas JSON.
        Thumbnail: no file created — thumbnail_ref stays null until first blur save.
        """
        self._wait_until_ready()
        res_id = res_id or str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        
        resources_dir = note_dir / ".sushi-resources"
        resources_dir.mkdir(exist_ok=True)

        if resource_type == "canvas":
            filename = f"{res_id}.jcanvas"
        elif resource_type == "thumbnail":
            res_id = f"{res_id}-thumb"
            filename = f"{res_id}.png"
        else:
            filename = f"{res_id}.{resource_type}"

        file_path = resources_dir / filename

        res_class = self._get_resource_class(resource_type)
        resource = res_class(
            resource_id=res_id,
            resource_type=resource_type,
            file_path=file_path,
            block_id=block_id,
            created_at=created_at
        )

        # Write blank state for canvas only — thumbnail has no file until first save
        if resource_type == "canvas":
            resource.regenerate()

        # Insert into DB
        cursor = self.db.conn.cursor()
        cursor.execute("""
            INSERT INTO resources (resource_id, resource_type, file_path, block_id, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (resource.resource_id, resource.resource_type, str(resource.file_path), resource.block_id, resource.created_at))
        self.db.conn.commit()

        log.debug("resource_created", resource_id=res_id, resource_type=resource_type, block_id=block_id)
        return resource

    # ══════════════════════════════════════════════════════════════════════════
    # RESOLVE — single gateway for path lookups with lazy integrity checks
    # ══════════════════════════════════════════════════════════════════════════

    def resolve_resource_path(
        self,
        filename: str,
        note_dir: Path,
        block_id: Optional[str] = None,
        block_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Single entry point for resolving a resource file path.

        Flow:
        1. Derive resource_id from filename stem.
        2. Look up in DB.
        3. If DB row exists and file exists on disk → return {"status": "ok", "path": str}.
        4. If DB row exists but file missing:
           - Canvas: regenerate blank file → return ok.
           - Thumbnail: if paired canvas exists, return regeneration_required payload
                        so frontend can re-render. If canvas also missing,
                        regenerate blank canvas, then return regeneration_required.
        5. If no DB row → create_resource, return ok.

        Args:
            filename: The resource filename (e.g. "abc123.jcanvas" or "abc123-thumb.png").
            note_dir: Parent directory of the .jnote file.
            block_id: Optional block_id for creating missing DB entries.
            block_data: Optional block data dict containing last_viewport etc.

        Returns:
            Dict with 'status' key: 'ok' | 'regeneration_required' | 'not_found'
        """
        self._wait_until_ready()

        res_id = Path(filename).stem
        resource_type = self._infer_type_from_filename(filename)
        
        resources_dir = note_dir / ".sushi-resources"
        expected_path = resources_dir / filename

        # Step 1: Look up in DB
        cursor = self.db.conn.cursor()
        row = cursor.execute(
            "SELECT * FROM resources WHERE resource_id = ?", (res_id,)
        ).fetchone()

        if row:
            resource = self._row_to_resource(row)
            
            if resource.exists():
                # Happy path — file exists and DB is consistent
                return {"status": "ok", "path": str(resource.file_path)}
            
            # DB entry exists but file is missing → lazy recovery
            return self._recover_missing_file(resource, note_dir, block_data)

        # No DB entry → create fresh resource if we have a block_id
        if block_id:
            log.info("resource_orphan_recreate", resource_id=res_id, block_id=block_id)
            # Determine the base UUID (strip -thumb suffix for thumbnails)
            base_res_id = res_id
            if resource_type == "thumbnail" and res_id.endswith("-thumb"):
                base_res_id = res_id[:-6]
            
            new_resource = self.create_resource(block_id, resource_type, note_dir, res_id=base_res_id)
            
            if resource_type == "thumbnail":
                # Even though we "created" a DB entry, there's no file yet.
                # Signal frontend to regenerate.
                return self._build_regeneration_payload(new_resource, note_dir, block_data)
            
            return {"status": "ok", "path": str(new_resource.file_path)}

        # Can't resolve — no DB entry and no block_id to auto-create
        return {"status": "not_found", "path": str(expected_path)}

    def _infer_type_from_filename(self, filename: str) -> str:
        """Infer resource type from filename extension/pattern."""
        if filename.endswith(".jcanvas"):
            return "canvas"
        elif filename.endswith(".png") and "-thumb" in filename:
            return "thumbnail"
        return "unknown"

    def _row_to_resource(self, row) -> Resource:
        """Hydrate a DB row into the correct Resource subclass."""
        res_class = self._get_resource_class(row["resource_type"])
        return res_class(
            resource_id=row["resource_id"],
            resource_type=row["resource_type"],
            file_path=Path(row["file_path"]),
            block_id=row["block_id"],
            created_at=row["created_at"]
        )

    def _recover_missing_file(
        self,
        resource: Resource,
        note_dir: Path,
        block_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Handle a resource that has a DB entry but no file on disk."""
        if resource.resource_type == "canvas":
            # Canvas missing → regenerate blank canvas JSON
            log.info("lazy_canvas_recovery", resource_id=resource.resource_id)
            resource.file_path.parent.mkdir(parents=True, exist_ok=True)
            resource.regenerate()
            return {"status": "ok", "path": str(resource.file_path)}

        if resource.resource_type == "thumbnail":
            return self._build_regeneration_payload(resource, note_dir, block_data)

        # Unknown type — just report not found
        return {"status": "not_found", "path": str(resource.file_path)}

    def _build_regeneration_payload(
        self,
        thumb_resource: Resource,
        note_dir: Path,
        block_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build the regeneration_required response for a missing thumbnail."""
        log.info("thumbnail_regeneration_required", resource_id=thumb_resource.resource_id)
        
        # Try to load canvas data from the paired canvas resource
        canvas_json = None
        canvas_res = self._get_paired_canvas_resource(thumb_resource.block_id)
        
        if canvas_res:
            if not canvas_res.exists():
                # Canvas also missing — regenerate blank
                canvas_res.file_path.parent.mkdir(parents=True, exist_ok=True)
                canvas_res.regenerate()
            try:
                canvas_json = json.loads(canvas_res.file_path.read_text(encoding="utf-8"))
            except Exception:
                canvas_json = None

        last_viewport = DEFAULT_VIEWPORT
        if block_data and isinstance(block_data.get("last_viewport"), dict):
            last_viewport = block_data["last_viewport"]

        return {
            "status": "regeneration_required",
            "canvas_data": canvas_json,
            "last_viewport": last_viewport,
        }

    # ══════════════════════════════════════════════════════════════════════════
    # READ / UPDATE / DELETE
    # ══════════════════════════════════════════════════════════════════════════

    def get_resource(self, resource_id: str, check_exists: bool = True) -> Resource:
        """Fetches resource from DB."""
        self._wait_until_ready()
        cursor = self.db.conn.cursor()
        row = cursor.execute("SELECT * FROM resources WHERE resource_id = ?", (resource_id,)).fetchone()
        if not row:
            raise ResourceNotFound(f"Resource {resource_id} not found in DB")

        resource = self._row_to_resource(row)

        if check_exists and not resource.exists():
            if resource.resource_type == "canvas":
                # Canvas missing → regenerate blank
                resource.file_path.parent.mkdir(parents=True, exist_ok=True)
                resource.regenerate()

        return resource

    def get_resources_for_block(self, block_id: str) -> List[Resource]:
        """Returns all resources mapped to a block."""
        self._wait_until_ready()
        cursor = self.db.conn.cursor()
        rows = cursor.execute("SELECT * FROM resources WHERE block_id = ?", (block_id,)).fetchall()
        return [self._row_to_resource(row) for row in rows]

    def update_resource(self, resource_id: str, content: Any):
        """Overwrites the file atomically. Does NOT create files — only updates existing resources."""
        self._wait_until_ready()
        resource = self.get_resource(resource_id, check_exists=False)
        
        if resource.resource_type == "thumbnail" and isinstance(content, str) and content.startswith("data:image"):
            resource.file_path.parent.mkdir(parents=True, exist_ok=True)
            save_data_url_as_png(content, resource.file_path)
            log.debug("thumbnail_resource_updated", resource_id=resource_id)
        else:
            # Assume content is a string or dict (canvas json)
            if isinstance(content, dict):
                content = json.dumps(content, indent=2)
            elif isinstance(content, bytes):
                resource.file_path.write_bytes(content)
                log.debug("binary_resource_updated", resource_id=resource_id)
                return
            atomic_write(resource.file_path, content)
            log.debug("text_resource_updated", resource_id=resource_id)

    def delete_resources_for_block(self, block_id: str):
        """Deletes all files and DB rows for a block."""
        self._wait_until_ready()
        resources = self.get_resources_for_block(block_id)
        for res in resources:
            if res.file_path.exists():
                try:
                    res.file_path.unlink()
                except OSError:
                    pass
        
        cursor = self.db.conn.cursor()
        cursor.execute("DELETE FROM resources WHERE block_id = ?", (block_id,))
        self.db.conn.commit()
        log.debug("resources_deleted_for_block", block_id=block_id, deleted_count=len(resources))

    def _get_paired_canvas_resource(self, block_id: str) -> Optional[CanvasResource]:
        """Helper to find the canvas resource paired with a block."""
        resources = self.get_resources_for_block(block_id)
        for res in resources:
            if res.resource_type == "canvas":
                return res
        return None

    # ══════════════════════════════════════════════════════════════════════════
    # SCAN — vault indexing
    # ══════════════════════════════════════════════════════════════════════════

    def scan_vault_incremental(self):
        """Incremental rebuild of in-memory resources from .jnote ground truth."""
        log.info("starting_incremental_resource_scan", vault_path=str(self.vault_path))
        
        # Look for .jnote files
        for root, _, files in os.walk(self.vault_path):
            root_path = Path(root)
            if ".sushi-resources" in root_path.parts:
                continue

            for file in files:
                if not file.endswith(".jnote"):
                    continue
                
                file_path = root_path / file
                try:
                    mtime_stat = file_path.stat().st_mtime
                    mtime_str = str(mtime_stat)
                except OSError:
                    continue
                
                note_id = file_path.stem
                if self.last_indexed.get(note_id) == mtime_str:
                    continue # unchanged
                
                self._index_note_resources(file_path, note_id)
                self.last_indexed[note_id] = mtime_str

        self._is_ready = True

    def _index_note_resources(self, file_path: Path, note_id: str):
        """Parses a note and inserts resources into the DB."""
        resources_dir = file_path.parent / ".sushi-resources"
        
        cursor = self.db.conn.cursor()
        cursor.execute("DELETE FROM resources WHERE file_path LIKE ?", (f"{resources_dir}%",))
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            self.db.conn.commit()
            return
            
        blocks = data.get("blocks", [])
        for block in blocks:
            b_id = block.get("block_id")
            b_data = block.get("data", {})
            b_type = block.get("type", "text")
            
            if b_type == "canvas":
                # Canvas Resource
                canvas_ref = b_data.get("canvas_ref")
                if canvas_ref:
                    res_id = Path(canvas_ref).stem
                    res_path = resources_dir / canvas_ref
                    cursor.execute("""
                        INSERT OR IGNORE INTO resources (resource_id, resource_type, file_path, block_id, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (res_id, "canvas", str(res_path), b_id, ""))
                
                # Thumbnail Resource — only index if thumbnail_ref is set (not null)
                thumb_ref = b_data.get("thumbnail_ref")
                if thumb_ref:
                    thumb_res_id = Path(thumb_ref).stem
                    res_path = resources_dir / thumb_ref
                    cursor.execute("""
                        INSERT OR IGNORE INTO resources (resource_id, resource_type, file_path, block_id, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (thumb_res_id, "thumbnail", str(res_path), b_id, ""))

        self.db.conn.commit()
