import uuid
from typing import Dict, Type
from pathlib import Path
import structlog

from sushi.resource_manager import ResourceManager

log = structlog.get_logger(__name__)

class BlockFactory:
    """Base factory for creating block schemas."""
    
    @classmethod
    def create(cls, note_id: str, resource_manager: ResourceManager, note_dir: Path, **kwargs) -> Dict:
        raise NotImplementedError("BlockFactory subclasses must implement create()")

    @classmethod
    def validate(cls, block_data: Dict) -> bool:
        """Validates the structure of the block data."""
        return "block_id" in block_data and "type" in block_data

    @classmethod
    def on_delete(cls, block_data: Dict, resource_manager: ResourceManager) -> None:
        """Handles any cleanup logic when a block is deleted."""
        pass


class TextBlock(BlockFactory):
    @classmethod
    def create(cls, note_id: str, resource_manager: ResourceManager, note_dir: Path, **kwargs) -> Dict:
        return {
            "block_id": str(uuid.uuid4()),
            "type": "text",
            "data": {
                "content": kwargs.get("content", ""),
                "format": kwargs.get("format", "markdown"),
            }
        }


class TodoBlock(BlockFactory):
    @classmethod
    def create(cls, note_id: str, resource_manager: ResourceManager, note_dir: Path, **kwargs) -> Dict:
        return {
            "block_id": str(uuid.uuid4()),
            "type": "todo",
            "data": {
                "content": kwargs.get("content", ""),
                "checked": kwargs.get("checked", False),
            }
        }


class CodeBlock(BlockFactory):
    @classmethod
    def create(cls, note_id: str, resource_manager: ResourceManager, note_dir: Path, **kwargs) -> Dict:
        return {
            "block_id": str(uuid.uuid4()),
            "type": "code",
            "data": {
                "code": kwargs.get("code", ""),
                "language": kwargs.get("language", "python"),
                "output": "",
            }
        }


class ImageBlock(BlockFactory):
    @classmethod
    def create(cls, note_id: str, resource_manager: ResourceManager, note_dir: Path, **kwargs) -> Dict:
        return {
            "block_id": str(uuid.uuid4()),
            "type": "image",
            "data": {
                "src": kwargs.get("src", ""),
                "caption": kwargs.get("caption", ""),
                "alignment": "center",
            }
        }


class LatexBlock(BlockFactory):
    @classmethod
    def create(cls, note_id: str, resource_manager: ResourceManager, note_dir: Path, **kwargs) -> Dict:
        return {
            "block_id": str(uuid.uuid4()),
            "type": "latex",
            "data": {
                "formula": kwargs.get("formula", ""),
                "display_mode": True,
            }
        }


class CanvasBlock(BlockFactory):
    @classmethod
    def create(cls, note_id: str, resource_manager: ResourceManager, note_dir: Path, **kwargs) -> Dict:
        """
        Canvas blocks require immediate allocation of their `.jcanvas` resource
        on the filesystem so the frontend can immediately mount the WASM canvas.
        
        Thumbnail is NOT created here — it is written on first blur after the user
        draws something. Until then, thumbnail_ref is null and the frontend shows
        a static placeholder asset.
        """
        block_id = str(uuid.uuid4())
        
        # Only create the canvas file — ResourceManager is the sole creator
        canvas_res = resource_manager.create_resource(block_id, "canvas", note_dir)
        
        return {
            "block_id": block_id,
            "type": "canvas",
            "data": {
                "canvas_ref": f"{canvas_res.resource_id}.jcanvas",
                "thumbnail_ref": None,
                "last_viewport": {
                    "offset_x": 0.0,
                    "offset_y": 0.0,
                    "scale": 1.0
                }
            }
        }

    @classmethod
    def on_delete(cls, block_data: Dict, resource_manager: ResourceManager) -> None:
        block_id = block_data.get("block_id")
        if block_id:
            resource_manager.delete_resources_for_block(block_id)


class UnifiedBlockFactory:
    """Unified access point for all block creation requests."""
    
    _FACTORIES: Dict[str, Type[BlockFactory]] = {
        "text": TextBlock,
        "todo": TodoBlock,
        "code": CodeBlock,
        "image": ImageBlock,
        "latex": LatexBlock,
        "canvas": CanvasBlock,
    }
    
    @classmethod
    def build_block(cls, block_type: str, note_id: str, resource_manager: ResourceManager, note_dir: Path, **kwargs) -> Dict:
        factory = cls._FACTORIES.get(block_type)
        
        if not factory:
            log.warning("unknown_block_type_requested", block_type=block_type)
            factory = TextBlock
            
        return factory.create(note_id=note_id, resource_manager=resource_manager, note_dir=note_dir, **kwargs)

    @classmethod
    def validate_block(cls, block_data: Dict) -> bool:
        block_type = block_data.get("type", "text")
        factory = cls._FACTORIES.get(block_type, TextBlock)
        return factory.validate(block_data)

    @classmethod
    def delete_block_resources(cls, block_data: Dict, resource_manager: ResourceManager):
        block_type = block_data.get("type", "text")
        factory = cls._FACTORIES.get(block_type, TextBlock)
        factory.on_delete(block_data, resource_manager)
