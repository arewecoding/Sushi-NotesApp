import os
from pathlib import Path
from sushi.cache_db import FileIndex
from sushi.resource_manager import ResourceManager
import json

def verify():
    # Arrange
    db = FileIndex()
    vault_path = Path("sample_notes")
    vault_path.mkdir(exist_ok=True)
    
    # Initialize Resource Manager
    rm = ResourceManager(db, vault_path)
    
    # 1. Verify `create_resource` writes blank .jcanvas to disk
    print("Testing create_resource...")
    res = rm.create_resource("block-123", "canvas", vault_path)
    
    assert res.file_path.exists(), "Blank .jcanvas was not written to disk"
    assert res.resource_type == "canvas"
    
    content = json.loads(res.file_path.read_text(encoding="utf-8"))
    assert "size" in content, "Blank canvas JSON is invalid"
    print(f"✅ create_resource passed. Created File: {res.file_path.name}")
    
    # 2. Verify the DB row is queryable via `get_resource`
    print("Testing get_resource...")
    fetched_res = rm.get_resource(res.resource_id)
    assert fetched_res.block_id == "block-123"
    print(f"✅ DB query passed. Fetched block_id: {fetched_res.block_id}")
    
    # Clean up test note
    res.file_path.unlink()

if __name__ == "__main__":
    verify()
