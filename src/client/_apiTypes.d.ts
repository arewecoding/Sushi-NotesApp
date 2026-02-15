/* eslint-disable */
/**
 * TypeScript types for PyTauri Notes App API
 * These match the Pydantic models in the Python backend.
 */

// Response types matching backend ipc_models.py
export interface NoteListItem {
    noteId: string;
    noteTitle: string;
}

export interface NoteBlockData {
    content?: string;
    code?: string;
    checked?: boolean;
    [key: string]: unknown;  // Allow additional properties
}

export interface NoteBlock {
    blockId: string;
    type: string;
    data: NoteBlockData;
    version: string;
    tags: string[];
    backlinks: string[];
}

export interface NoteContent {
    noteId: string;
    title: string;
    blocks: NoteBlock[];
}

export interface OperationResponse {
    success: boolean;
    message: string;
    data?: Record<string, unknown>;
}

// Directory tree types
export interface DirectoryItem {
    dirPath: string;
    dirName: string;
}

export interface DirectoryContents {
    subdirs: DirectoryItem[];
    notes: NoteListItem[];
}

export interface GetDirectoryRequest {
    dirPath?: string | null;
}

// Request types
export interface OpenNoteRequest {
    noteId: string;
}

export interface CreateNoteRequest {
    title: string;
}

export interface CreateBlockRequest {
    noteId: string;
    blockType: string;
    contentData: Record<string, unknown>;
}

export interface UpdateBlockRequest {
    noteId: string;
    blockId: string;
    newData: Record<string, unknown>;
}

export interface DeleteBlockRequest {
    noteId: string;
    blockId: string;
}

export interface UpdateNoteContentRequest {
    noteId: string;
    title: string;
    blocks: NoteBlock[];
}

export interface CreateNoteInDirRequest {
    title: string;
    dirPath: string;
}

export interface DeleteNoteRequest {
    noteId: string;
}

export interface DeleteDirectoryRequest {
    dirPath: string;
}

export interface MoveItemRequest {
    sourcePath: string;
    destDir: string;
}

export interface DuplicateNoteRequest {
    noteId: string;
}

export interface CreateDirectoryRequest {
    parentPath: string;
    dirName: string;
}

export interface MoveNoteRequest {
    noteId: string;
    destDir: string;
}

export interface RenameNoteRequest {
    noteId: string;
    newTitle: string;
}

export interface RenameDirectoryRequest {
    dirPath: string;
    newName: string;
}

// Commands interface for type-safe API calls
export interface Commands {
    get_directory_contents: {
        input: GetDirectoryRequest;
        output: DirectoryContents;
    };
    get_sidebar: {
        input: null;
        output: NoteListItem[];
    };
    open_note: {
        input: OpenNoteRequest;
        output: NoteContent | null;
    };
    update_note_content: {
        input: UpdateNoteContentRequest;
        output: OperationResponse;
    };
    create_note: {
        input: CreateNoteRequest;
        output: NoteListItem | null;
    };
    add_block: {
        input: CreateBlockRequest;
        output: OperationResponse;
    };
    update_block: {
        input: UpdateBlockRequest;
        output: OperationResponse;
    };
    delete_block: {
        input: DeleteBlockRequest;
        output: OperationResponse;
    };
    create_note_in_dir: {
        input: CreateNoteInDirRequest;
        output: NoteListItem | null;
    };
    delete_note_cmd: {
        input: DeleteNoteRequest;
        output: OperationResponse;
    };
    delete_directory_cmd: {
        input: DeleteDirectoryRequest;
        output: OperationResponse;
    };
    move_item_cmd: {
        input: MoveItemRequest;
        output: OperationResponse;
    };
    duplicate_note_cmd: {
        input: DuplicateNoteRequest;
        output: NoteListItem | null;
    };
    create_directory_cmd: {
        input: CreateDirectoryRequest;
        output: OperationResponse;
    };
    move_note_cmd: {
        input: MoveNoteRequest;
        output: OperationResponse;
    };
    rename_note_cmd: {
        input: RenameNoteRequest;
        output: OperationResponse;
    };
    rename_directory_cmd: {
        input: RenameDirectoryRequest;
        output: OperationResponse;
    };
}
