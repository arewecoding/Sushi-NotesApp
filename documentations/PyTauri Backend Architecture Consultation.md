# **Architectural Modernization and Strategic Refactoring for High-Performance Local-First Applications**

## **Executive Summary**

The transition from a functional prototype to a robust, scalable desktop application requires a fundamental shift in architectural thinking. This is particularly true for applications leveraging the PyTauri framework, which occupies a unique intersection between the high-performance, memory-safe execution environment of Rust and the dynamic, rich ecosystem of Python. The current backend implementation of the "Sushi" Notes App 1 demonstrates a working understanding of the PyTauri interoperability model, utilizing PyO3 for embedded execution and anyio for asynchronous bridging. However, the existing codebase exhibits characteristics typical of early-stage software: strict coupling between interface adapters and business logic, a monolithic service structure, and hardcoded infrastructure dependencies. These traits, while expedient for initial development, pose significant barriers to the user's stated goal of adding complex future functionality and ensuring robust readability.  
This report presents an exhaustive architectural analysis and modernization strategy. It advocates for the adoption of a Clean Architecture (Hexagonal) approach, specifically tailored to the constraints and capabilities of the PyTauri environment. By decoupling the core business logic (Domain) from the persistence mechanism (Infrastructure) and the user interface (Tauri/Frontend), the system can achieve a level of plasticity that supports future requirements—such as cloud synchronization, full-text search, or database migration—without necessitating rewrites of the core application logic.  
The analysis is structured to first audit the existing codebase against industry best practices for local-first software, identifying specific fragility points such as the "God Class" anti-pattern observed in the VaultService and the implicit state management within the module scope. Subsequently, it proposes a comprehensive refactoring roadmap centered on the Repository Pattern, Command-Query Responsibility Segregation (CQRS), and rigorous Dependency Injection (DI). This strategy prioritizes the "Software Architect" perspective, focusing on long-term maintainability, type safety via strict boundaries, and the preservation of the "Local-First" ethos through resilient file system interactions.

## ---

**1\. Architectural Audit of the Existing System**

To prescribe a robust future architecture, one must first perform a forensic examination of the current implementation. The "Sushi" backend functions within a specific execution context: the PyTauri sidecarless model. Unlike traditional sidecar architectures where Python runs as a sub-process communicating via standard I/O 2, this application embeds the Python interpreter directly into the Rust process memory space.5 This affords zero-latency communication but demands strict adherence to thread safety and memory management disciplines which are currently under-addressed.

### **1.1 The Monolithic Service Anti-Pattern**

A central finding of the audit is the excessive responsibility concentration within the VaultService class located in active\_state.py.1 In software architecture, this is often referred to as a "God Object" or "God Class." This single entity is currently responsible for a disparate array of system concerns that should, in a mature system, be segregated.  
The VaultService manages low-level file path resolution, constructing paths using self.vault\_path / f"{note\_id}.json". Simultaneously, it handles high-level application state, maintaining the \_active\_notes dictionary which serves as an in-memory session cache. It also executes business logic, such as the manipulation of blocks within a note (adding, updating, deleting), and finally, it performs infrastructure-level persistence operations via json.dump and json.load.  
This violation of the Single Responsibility Principle (SRP) creates a brittle system. If the developer wishes to change the storage format from JSON to Markdown or SQLite in the future—a likely requirement for a scaling note-taking app—the VaultService would require a complete rewrite. Because the business rules (e.g., "a note must have a title") are intertwined with the storage logic (e.g., "write bytes to disk"), it becomes impossible to modify one without risking regression in the other. Furthermore, this coupling makes unit testing nearly impossible without mocking the entire file system, as the service cannot be instantiated without a valid path and immediately attempts to interact with the OS.

### **1.2 Infrastructure Leakage and Hardcoded Dependencies**

A critical barrier to portability and collaboration is identified in the hardcoded configuration paths. The codebase explicitly defines the vault path as Path("C:/Users/ADMIN/Documents/SushiVault") within the VaultService.1 This strict dependency on a specific Windows user directory renders the application non-portable to other environments (Linux, macOS) or even other users on the same operating system.  
In a professional architecture, infrastructure details such as file paths must be externalized. The application logic should strictly operate on abstract locations provided by a configuration service or environment variables. The current implementation violates the "Configuration as Code" principle by embedding environmental constants directly into the compiled source. This not only hampers cross-platform deployment—a key selling point of Tauri 6—but also prevents the implementation of different environments (Development, Testing, Production) which is essential for safe iteration.7

### **1.3 State Management and Concurrency Risks**

The current state management strategy relies on a module-level global variable state in \_\_init\_\_.py, initialized inside the setup function.1 While this effectively singleton pattern ensures only one state exists, it creates implicit dependencies that are invisible to the function signatures. Functions in \_\_init\_\_.py access state.service directly, relying on the side-effect of the setup function having run previously.  
More critically, the concurrency model exhibits potential race conditions. The application uses anyio to bridge the async Tauri commands with the synchronous file I/O. However, the ActiveNote class and VaultService manipulate shared dictionaries (\_active\_notes) without explicit locking mechanisms visible in the snippets. In a local-first application, the file system is a shared resource; an external process (like a cloud sync agent or a user editing a file manually) could modify a note file while the application is writing to it. The current architecture lacks a "Reconciliation Layer" to arbitrate these conflicts, risking data loss or corruption if the internal state drifts from the file system state.9

### **1.4 Interface Logic Coupling**

The codebase exhibits "Leaky Abstractions" at the interface boundary. The \_\_init\_\_.py file contains a utility function dict\_to\_camel which recursively transforms dictionary keys from snake\_case to camelCase for JavaScript compatibility.1 This transformation logic is manually invoked within command handlers.  
This mixing of presentation logic (formatting data for the frontend) with control logic (executing commands) violates the separation of concerns. If the frontend framework changes or if a specific API contract requires a different aliasing strategy, every command handler would need to be updated. In a robust architecture, serialization and data transformation are handled transparently by a dedicated serialization layer or Interface Adapter, ensuring that the core backend code remains Pythonic (snake\_case) and ignorant of the frontend's naming conventions.

### **1.5 Analysis of Data Structures**

The application currently relies on ipc\_models.py and note\_schema.py to define data structures.1 While the use of Pydantic is a positive choice for validation 11, the distinction between "Domain Entities" (internal business objects) and "Data Transfer Objects" (DTOs for communication) is blurred. The JNote class appears to serve as both the disk format and the internal representation. This means that any change to the file format (e.g., renaming a field for optimization) forces a change in the internal logic, and vice versa. This tight coupling between the persistent representation and the volatile memory representation is a primary source of technical debt in growing applications.

## ---

**2\. The Proposed Paradigm: Clean Architecture for PyTauri**

To address the identified deficiencies and prepare the codebase for significant future expansion, the adoption of Clean Architecture (also known as Ports and Adapters) is recommended. This architectural style emphasizes the separation of software into layers, with the dependency rule stating that source code dependencies can only point inwards. Nothing in an inner circle can know anything at all about something in an outer circle.

### **2.1 The Dependency Rule Applied**

In the context of the Sushi app, the "Inner Circle" is the Domain—the concept of a Note, a Block, and the rules that govern them. The "Outer Circle" is the Infrastructure—the File System, the Tauri API, and the specific database used for caching.

| Layer | Responsibility | Components in Sushi |
| :---- | :---- | :---- |
| **1\. Domain (Core)** | Enterprise Business Rules. Pure Python. No frameworks. | Note, Block, BlockType, NoteRepository (Interface) |
| **2\. Application** | Application Business Rules. Orchestration of data flow. | CreateNoteUseCase, GetSidebarUseCase, SearchNotesUseCase |
| **3\. Interface Adapters** | Conversion of data between Core and External formats. | TauriController (Commands), Serializers, DTOs |
| **4\. Infrastructure** | Frameworks, Drivers, Tools. The physical world. | FileSystemRepository, SQLiteCache, PyTauri bindings, Config |

### **2.2 Domain-Centric Design**

The refactoring begins by isolating the Domain. Currently, logic is scattered across VaultService and command handlers. In the new architecture, the Domain layer will define the *capabilities* of the system independent of execution. For instance, the logic that "A Block cannot be added to a non-existent Note" belongs in the Domain, not in the filesys.py or \_\_init\_\_.py files.  
This separation allows for "Subcutaneous Testing." We can test the entire logic of the note-taking application—creating notes, moving blocks, searching—using standard pytest suites without ever launching the Tauri GUI or creating real files on the hard drive. This drastic improvement in testability is the hallmark of professional software architecture.12

### **2.3 The Role of PyTauri in Clean Architecture**

It is crucial to define where PyTauri fits. In this architecture, PyTauri is an *external detail*. It is a delivery mechanism, much like HTTP is for a web server. The Python backend should not be "a PyTauri app"; it should be a "Note Taking App" that happens to be delivered via PyTauri. This distinction is vital because it prevents vendor lock-in. If, in the future, the requirements shift to a web-based backend using FastAPI or a CLI tool, the Domain and Application layers can be reused entirely, with only the Interface Adapter layer needing replacement.12

## ---

**3\. Domain Modeling and Data Integrity**

The foundation of the modernized architecture lies in a rigorous definition of the Domain Model. The current JNote implementation in note\_schema.py 1 is a Pydantic model that mirrors the JSON structure. While Pydantic is powerful, using it for domain entities can lead to "Anemic Domain Models"—objects that contain data but no behavior.

### **3.1 Rich Domain Entities**

We propose elevating the core concepts to **Rich Entities**. A Note should not just be a dictionary of data; it should be a class that ensures its own consistency.  
The Note entity acts as an **Aggregate Root**. It creates a consistency boundary. External objects cannot hold references to internal Blocks directly; they must go through the Note to modify them. This ensures that operations like "Reorder Blocks" or "Delete Block" are transactional within the scope of the Note. If a block is moved, the Note entity ensures the indices of all other blocks are updated correctly before the state is committed.  
Contrast this with the current VaultService.delete\_block 1, which likely manually splices a list. If that logic is duplicated in another service (e.g., a "Bulk cleanup" script), the logic might drift. By encapsulating it in the Note.remove\_block() method, the logic exists in exactly one place.

### **3.2 Value Objects for Type Safety**

The current application uses primitive types (strings) for identifiers (note\_id: str). This is prone to error; a function expecting a block\_id could accidentally receive a note\_id, and the interpreter would not complain until runtime failure.  
The modernized architecture introduces **Value Objects** for these identifiers.

* NoteID: A distinct type wrapping a UUID.  
* BlockID: A distinct type wrapping a hash or UUID.

These Value Objects are immutable. When passed into methods, they guarantee type safety. For example, the signature add\_block(target: NoteID, block: BlockContent) makes it statically impossible to pass a block ID as the target. This utilizes Python's type hinting system to its fullest extent, reducing bugs before the code runs.

### **3.3 Decoupling Data Transfer Objects (DTOs)**

A distinct separation must be enforced between the objects used for storage (Infrastructure), the objects used for logic (Domain), and the objects used for communication (API).

* **Persistence DTOs:** These mirror the exact structure of the files on disk (e.g., snake\_case JSON fields). They are optimized for storage efficiency.  
* **Domain Entities:** These are optimized for Python manipulation (e.g., using datetime objects instead of ISO strings).  
* **API DTOs:** These mirror the expectations of the Frontend (e.g., camelCase fields).

The current ipc\_models.py 1 mixes these concerns. By separating them, we gain the freedom to refactor. We could change the disk format to use short keys (t instead of title) to save space, without breaking the frontend which expects title. Mappers in the Interface Adapter layer handle the translation between these forms.15

## ---

**4\. Interface Adapters and The Repository Pattern**

The most significant structural change recommended is the implementation of the **Repository Pattern**. This pattern mediates between the domain and data mapping layers using a collection-like interface for accessing domain objects. It completely abstracts the underlying file system or database.18

### **4.1 Abstraction of Storage**

Currently, the VaultService knows it is reading JSON files. This violates the Open-Closed Principle. To add SQL support, one would have to modify the service.  
The proposed architecture defines an abstract interface NoteRepository in the Domain layer:

Python

class NoteRepository(ABC):  
    @abstractmethod  
    def get\_by\_id(self, id: NoteID) \-\> Note:...  
    @abstractmethod  
    def save(self, note: Note) \-\> None:...  
    @abstractmethod  
    def delete(self, id: NoteID) \-\> None:...

The *implementation* of this interface, FileSystemNoteRepository, resides in the Infrastructure layer. It contains all the logic currently in filesys.py—open(), json.load(), path joining. The Domain layer calls repo.get\_by\_id(), completely unaware of whether that data came from a JSON file, a Postgres database, or a cloud API.

### **4.2 Handling PyTauri Constraints via Repositories**

PyTauri applications operate in a shared memory space. The Repository implementation can be optimized for this.

* **Memory Mapping:** For read-heavy operations, the repository can implement memory mapping strategies or hold a read-through cache (LRU) to avoid hitting the disk for every request.  
* **Active State Integration:** The Repository becomes the natural guardian of the ActiveState logic found in active\_state.py.1 When get\_by\_id is called, the Repository first checks the active session. If the note is open and dirty (unsaved), it returns the in-memory version. If not, it reads from disk. This centralizes the "Source of Truth" logic which is currently scattered.

### **4.3 Comparison: Active Record vs. Repository**

Some Python frameworks (like Django) use the Active Record pattern, where the model knows how to save itself (note.save()). For a desktop application with complex file interactions, this is an anti-pattern. Active Record couples the entity to the database. The Repository pattern is superior here because it allows the Note entity to remain a Pure Python Object (POJO), which is essential for the "Local-First" requirement where data might be synced, merged, or versioned by external tools. The entity shouldn't care about file locks; the Repository should.21

### **4.4 Managing Search Indices**

The cache\_db.py 1 suggests an intent to index notes. In the Repository pattern, the NoteRepository implementation can seamlessly write to *both* the file system and the search index.

* **Write Operation:** repo.save(note) \-\> Serializes to JSON file \-\> Updates SQLite FTS index.  
* **Transactionality:** The repository ensures these happen together, or rolls back. This keeps the search sidebar in sync with the file content, addressing the "stale data" problem inherent in separate indexing processes.

## ---

**5\. Application Logic and CQRS**

As the application grows, the read and write models often diverge. The data you need to *render the sidebar* (ID, Title, Icon, Tag) is different from the data you need to *edit a note* (Full block content, history).

### **5.1 Command-Query Responsibility Segregation (CQRS)**

The proposed architecture splits the application logic into **Commands** (Write) and **Queries** (Read).

* **Commands:** CreateNote, UpdateBlock, DeleteNote. These use the NoteRepository to load the full entity, modify it, and save it. They enforce strict business rules.  
* **Queries:** GetSidebar, SearchNotes. These bypass the potentially heavy Note entity loading. Instead, they interact with a specialized **Read Model** (e.g., the SQLite index maintained by cache\_db.py).

This separation solves a key performance bottleneck in local-first apps. Generating the sidebar by opening and parsing 1,000 JSON files (using the standard Domain path) would be prohibitively slow. By using a CQRS Query that reads from a pre-computed SQLite index, the operation becomes instantaneous ($O(1)$ vs $O(N)$), while the Command side maintains the purity of the file-based storage.19

### **5.2 Use Case Interactors**

Instead of methods on VaultService, each action becomes a class (a Use Case Interactor).

* class AddBlockUseCase:  
  * **Input:** AddBlockDTO (validated by Pydantic).  
  * **Logic:**  
    1. Retrieve Note via Repository.  
    2. Call note.add\_block().  
    3. Save Note via Repository.  
  * **Output:** BlockAddedDTO.

This "Vertical Slicing" of functionality makes the code highly readable. To understand how blocks are added, a developer opens add\_block\_use\_case.py and sees the entire flow, rather than searching through a 2,000-line Service class. It also simplifies dependency management; this Use Case only needs the NoteRepository, not the ConfigService or LogService.

## ---

**6\. Concurrency, State, and Synchronization**

PyTauri introduces specific concurrency challenges due to the Global Interpreter Lock (GIL) and the interaction with Rust's async runtime. The audit revealed usage of anyio.start\_blocking\_portal 1, which is correct for bridging, but the strategy for state protection needs fortification.

### **6.1 The "Two Generals" Problem in Local-First Apps**

A defining characteristic of the "Sushi" app is that it watches the file system for changes (filesys.py). This introduces a race condition known as the "Two Generals" problem.

* **Scenario:** The user is typing in the app (modifying the in-memory ActiveNote). Simultaneously, an external sync client (e.g., Dropbox) updates the underlying JSON file.  
* **Current Risk:** If the app saves, it overwrites Dropbox. If the app reloads, the user loses their typing.

The modernized architecture handles this in the **Application Layer**:

1. **Versioning:** The ActiveNote tracks a last\_modified\_timestamp or a content hash of the file when it was loaded.  
2. **Optimistic Locking:** When save() is called, the Repository checks if the file on disk has changed since load.  
3. **Conflict Strategy:**  
   * If changed: The save fails. The architecture raises a ConcurrentModificationException.  
   * The Controller catches this and sends a specific error code to the frontend.  
   * The Frontend presents a Merge UI ("Keep Yours" vs. "Accept Incoming").

### **6.2 Offloading Blocking I/O**

While json.dump is fast for small files, it is a blocking I/O operation. In PyTauri, holding the GIL during file I/O freezes the Python logic. The Refactored Infrastructure layer should utilize anyio.to\_thread.run\_sync to execute Repository save methods in a worker thread. This releases the reactor loop to handle other incoming IPC messages (like "Cancel" or "Navigate"), maintaining UI responsiveness.23

### **6.3 Eventual Consistency for the Sidebar**

Updates to the sidebar (the Read Model) should be eventually consistent. When a save() completes, the Repository emits a domain event NoteSaved. A background listener catches this and updates the SQLite index. This ensures that the user's write operation is not slowed down by the overhead of updating the search index; that happens milliseconds later in the background.

## ---

**7\. Dependency Injection and System Bootstrapping**

The global state in \_\_init\_\_.py is a major hindrance to testing and modularity. The solution is **Dependency Injection (DI)**.

### **7.1 Inversion of Control (IoC) Container**

Instead of modules importing each other, we introduce a Container class (the Composition Root). This class is responsible for instantiating all dependencies and wiring them together.

Python

class Container:  
    def \_\_init\_\_(self):  
        \# 1\. Configuration  
        self.config \= ConfigService()   
          
        \# 2\. Infrastructure  
        self.db\_driver \= SQLiteDriver(self.config.db\_path)  
        self.fs\_repo \= FileSystemNoteRepository(self.config.vault\_path)  
          
        \# 3\. Application Use Cases (Injecting Infrastructure)  
        self.get\_sidebar \= GetSidebarUseCase(repo=self.db\_driver)  
        self.save\_note \= SaveNoteUseCase(repo=self.fs\_repo)

### **7.2 Bootstrapping the PyTauri App**

The setup function in \_\_init\_\_.py now becomes simple. It instantiates the Container and stores it. The command handlers strictly retrieve use cases from this container.

Python

@commands.command()  
async def save\_note(request: SaveNoteRequest) \-\> Response:  
    \# Resolve dependency  
    use\_case \= container.save\_note  
    \# Execute  
    result \= await use\_case.execute(request)  
    return serialize(result)

This "Inversion of Control" means that for unit tests, we can instantiate a TestContainer that injects a InMemoryNoteRepository instead of the file system. We can then test the entire application logic without touching the disk, making the test suite milliseconds fast and highly reliable.25

## ---

**8\. Future-Proofing: Scalability and Extensions**

The user explicitly requested architecture robust for "adding much more stuff later." The proposed Clean Architecture is specifically designed for this extensibility.

### **8.1 Plugin Architecture**

By standardizing the **Use Case** interface, we can introduce a **Middleware** or **Pipeline** pattern.

* **Requirement:** "I want to add an AI summarizer that runs every time a note is saved."  
* **Implementation:** We do not modify SaveNoteUseCase. Instead, we register a PostSaveHook. The CommandBus executes the save, and then iterates through registered hooks. The AI plugin lives in a separate module, subscribed to the NoteSaved event.

### **8.2 Switching Search Engines**

Currently, search is likely a simple iteration or basic SQL query. As the note vault grows to 10,000+ notes, this will degrade.

* **Future Path:** Switch to **Tantivy** (a Rust-based search engine, highly compatible with Tauri) or **Lucene**.  
* **Implementation:** Create a new implementation of SearchRepository (e.g., TantivySearchRepository). Update the Container to inject this new class. The rest of the application (Frontend, Domain, Commands) remains completely unaware of the change.

### **8.3 Cloud Synchronization**

The separation of the Note entity from the FileSystemRepository allows for the introduction of a CloudSyncService. This service can poll the Repository for changes (using the Event Bus) and push them to an API. Because the Domain Layer ensures data integrity, the sync service can rely on valid data structures without defensive programming.

## ---

**9\. Implementation Roadmap**

To transition from the current 1 codebase to this architectural vision, a phased approach is recommended to avoid "The Big Rewrite" paralysis.

### **Phase 1: Sanitation and Configuration**

1. **Configuration Service:** Replace hardcoded paths in active\_state.py with a ConfigService that respects OS standards (XDG on Linux, AppData on Windows).  
2. **Schema Extraction:** Move all Pydantic models out of ipc\_models.py into a dedicated schemas package. Separate them into Input (Request) and Output (Response) schemas.

### **Phase 2: The Core Abstraction**

3. **Domain Entities:** Create the Note class in a domain package. Write pure Python tests for it.  
4. **Repository Interface:** Define the NoteRepository ABC.  
5. **Repository Implementation:** Refactor filesys.py into FileSystemNoteRepository, implementing the interface. Ensure it passes the integration tests.

### **Phase 3: Wiring and Injection**

6. **Dependency Container:** Implement the basic DI container.  
7. **Service Decomposition:** Break VaultService apart. Move the logic for "Opening a Note" into OpenNoteUseCase and wire it up in the container.  
8. **Command Refactoring:** Update one command (e.g., open\_note) in \_\_init\_\_.py to use the container.

### **Phase 4: Full CQRS**

9. **Read Model:** Formalize the cache\_db.py into a SidebarQueryService.  
10. **Command Migration:** Move the remaining write operations (add\_block, etc.) to Use Cases.

### **Phase 5: Advanced Concurrency**

11. **Event Bus:** Implement the internal event system to handle file watcher updates.  
12. **Locking:** Apply granular locking in the ActiveState to handle the race conditions identified in the audit.

By strictly adhering to these phases, the "Sushi" application will evolve into a professional-grade software product. The resulting architecture will be characterized by high readability, ease of testing, and the flexibility to accommodate whatever future requirements emerge, fulfilling the software architect's mandate for robustness and design excellence.

#### **Works cited**

1. combined\_code.md  
2. Embedding External Binaries \- Tauri, accessed February 12, 2026, [https://v2.tauri.app/develop/sidecar/](https://v2.tauri.app/develop/sidecar/)  
3. Embedding External Binaries | Tauri v1, accessed February 12, 2026, [https://tauri.app/v1/guides/building/sidecar](https://tauri.app/v1/guides/building/sidecar)  
4. how to use tauri app and python script as a back end \- Stack Overflow, accessed February 12, 2026, [https://stackoverflow.com/questions/75913627/how-to-use-tauri-app-and-python-script-as-a-back-end](https://stackoverflow.com/questions/75913627/how-to-use-tauri-app-and-python-script-as-a-back-end)  
5. pytauri/pytauri: Tauri binding for Python through Pyo3 \- GitHub, accessed February 12, 2026, [https://github.com/pytauri/pytauri](https://github.com/pytauri/pytauri)  
6. tauri-apps/tauri: Build smaller, faster, and more secure desktop and mobile applications with a web frontend. \- GitHub, accessed February 12, 2026, [https://github.com/tauri-apps/tauri](https://github.com/tauri-apps/tauri)  
7. Best Practices for Implementing Configuration Class in Python | by VerticalServe Blogs, accessed February 12, 2026, [https://verticalserve.medium.com/best-practices-for-implementing-configuration-class-in-python-b63b70048cc5](https://verticalserve.medium.com/best-practices-for-implementing-configuration-class-in-python-b63b70048cc5)  
8. Working with Python Configuration Files: Tutorial & Best Practices \- Configu, accessed February 12, 2026, [https://configu.com/blog/working-with-python-configuration-files-tutorial-best-practices/](https://configu.com/blog/working-with-python-configuration-files-tutorial-best-practices/)  
9. A Beginner's Guide to Local-First Software Development \- OpenReplay Blog, accessed February 12, 2026, [https://blog.openreplay.com/beginners-guide-local-first-software-development/](https://blog.openreplay.com/beginners-guide-local-first-software-development/)  
10. Some notes on local-first development | Hacker News, accessed February 12, 2026, [https://news.ycombinator.com/item?id=37488034](https://news.ycombinator.com/item?id=37488034)  
11. Welcome to Pydantic \- Pydantic Validation, accessed February 12, 2026, [https://docs.pydantic.dev/latest/](https://docs.pydantic.dev/latest/)  
12. Clean Architecture with Python. Build testable, scalable and… | by Raman Shaliamekh | Medium, accessed February 12, 2026, [https://medium.com/@shaliamekh/clean-architecture-with-python-d62712fd8d4f](https://medium.com/@shaliamekh/clean-architecture-with-python-d62712fd8d4f)  
13. Clean architectures in Python: a step-by-step example \- The Digital Cat, accessed February 12, 2026, [https://www.thedigitalcatonline.com/blog/2016/11/14/clean-architectures-in-python-a-step-by-step-example/](https://www.thedigitalcatonline.com/blog/2016/11/14/clean-architectures-in-python-a-step-by-step-example/)  
14. How to write and package desktop apps with Tauri \+ Vue \+ Python \- Senhaji Rhazi hamza, accessed February 12, 2026, [https://hamza-senhajirhazi.medium.com/how-to-write-and-package-desktop-apps-with-tauri-vue-python-ecc08e1e9f2a](https://hamza-senhajirhazi.medium.com/how-to-write-and-package-desktop-apps-with-tauri-vue-python-ecc08e1e9f2a)  
15. Converting DTOs to Entities in Clean Architecture: Exploring Best Practices with GRASP | by Estíver Hipólito | Medium, accessed February 12, 2026, [https://medium.com/@estiverherrerahipolito/converting-dtos-to-entities-in-clean-architecture-exploring-best-practices-with-grasp-9e335f99e361](https://medium.com/@estiverherrerahipolito/converting-dtos-to-entities-in-clean-architecture-exploring-best-practices-with-grasp-9e335f99e361)  
16. Best practices for using DTOs (Data Transfer Objects) in a clean architecture \- Leaders Tec, accessed February 12, 2026, [https://leaders.tec.br/article/3466ab](https://leaders.tec.br/article/3466ab)  
17. Clean Architecture with DTOs.. When building REST API's with… | by Gmatieso \- Medium, accessed February 12, 2026, [https://medium.com/@matiesogeoffrey/clean-architecture-with-dtos-24f543f850fb](https://medium.com/@matiesogeoffrey/clean-architecture-with-dtos-24f543f850fb)  
18. Factory and Repository Pattern with SQLAlchemy and Pydantic : r/Python \- Reddit, accessed February 12, 2026, [https://www.reddit.com/r/Python/comments/1aiyken/factory\_and\_repository\_pattern\_with\_sqlalchemy/](https://www.reddit.com/r/Python/comments/1aiyken/factory_and_repository_pattern_with_sqlalchemy/)  
19. Repository Pattern \- Cosmic Python, accessed February 12, 2026, [https://www.cosmicpython.com/book/chapter\_02\_repository.html](https://www.cosmicpython.com/book/chapter_02_repository.html)  
20. The Repository Pattern Done Right \- Matias Navarro-Carter: The Chilean Nerd, accessed February 12, 2026, [https://blog.mnavarro.dev/the-repository-pattern-done-right](https://blog.mnavarro.dev/the-repository-pattern-done-right)  
21. Active Record Pattern vs. Repository Pattern: Making the Right Choice | by shiiyan \- Medium, accessed February 12, 2026, [https://medium.com/@shiiyan/active-record-pattern-vs-repository-pattern-making-the-right-choice-f36d8deece94](https://medium.com/@shiiyan/active-record-pattern-vs-repository-pattern-making-the-right-choice-f36d8deece94)  
22. Active Record verses Repository, accessed February 12, 2026, [https://moleseyhill.com/2009-07-13-active-record-verses-repository.html](https://moleseyhill.com/2009-07-13-active-record-verses-repository.html)  
23. Python desktop applications with asynchronous features (part 1\) \- Schneide Blog, accessed February 12, 2026, [https://schneide.blog/2024/12/16/python-desktop-applications-with-asynchronous-features-part-1/](https://schneide.blog/2024/12/16/python-desktop-applications-with-asynchronous-features-part-1/)  
24. Mastering Asynchronous Programming in Python: A Beginner-Friendly Guide, accessed February 12, 2026, [https://dev.to/fludapp/mastering-asynchronous-programming-in-python-a-beginner-friendly-guide-lm](https://dev.to/fludapp/mastering-asynchronous-programming-in-python-a-beginner-friendly-guide-lm)  
25. Why I Started Using Dependency Injection in Python | by Haymang Ahuja | Level Up Coding, accessed February 12, 2026, [https://levelup.gitconnected.com/why-i-started-using-dependency-injection-in-python-bff304fb851b](https://levelup.gitconnected.com/why-i-started-using-dependency-injection-in-python-bff304fb851b)  
26. Dependency Injection: a Python Way \- Rost Glukhov | Personal site and technical blog, accessed February 12, 2026, [https://www.glukhov.org/post/2025/12/dependency-injection-in-python/](https://www.glukhov.org/post/2025/12/dependency-injection-in-python/)