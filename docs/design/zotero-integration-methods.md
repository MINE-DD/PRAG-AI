# PRAG × Zotero Integration Methods Research

> Research scope: Only native Zotero mechanisms (excluding third-party plugins such as Better BibTeX), covering only Zotero 7 and Zotero 8.
>
> Research date: March 2026. Zotero 8 was officially released on January 22, 2026, with the latest version being 8.0.3 (February 7, 2026).

---

## 1. Key Changes from Zotero 7 to 8

| Dimension | Zotero 7 | Zotero 8 |
|------|----------|----------|
| Internal platform | Firefox 115 (ESR) | Firefox 140 |
| Module system | JSM (.jsm) | **ES Modules (.mjs/.sys.mjs)** |
| Promise library | Bluebird | Standard JS Promise |
| Plugin architecture | Bootstrapped extension | Bootstrapped extension (unchanged) |
| Local API | Basic read access (introduced in beta 88) | Extended: `/fulltext` endpoint + annotation support |
| Plugin API | ItemTreeManager, ItemPaneManager, Reader, PreferencePanes | Added **MenuManager** (custom context menus) |
| Release cadence | Slower | One release every 6–10 weeks |
| Plugin stability commitment | No explicit commitment | **"New stable APIs should remain stable across multiple future versions"** |

**Impact on PRAG**: If developing a Zotero plugin, be aware of the JSM → ESM migration. Core integration mechanisms (Local API, HTTP Server, Notifier, Server.Endpoints) remain compatible between 7 and 8.

---

## 2. All Native Zotero Integration Methods

### 2.1 Local API (Local REST API)

**Overview**: An HTTP service running on `http://127.0.0.1:23119/api/` within the Zotero desktop client, mirroring the Web API v3 interface format but operating entirely locally.

**How to enable**: Settings → Advanced → "Allow other applications on this computer to communicate with Zotero"

**Available versions**: Zotero 7 (introduced in beta 88), Zotero 8 (extended with fulltext and annotation endpoints)

**Endpoint list**:

```
/api/users/0/items                    → All items (0 = current user)
/api/users/0/items/top                → Top-level items
/api/users/0/items/trash              → Trash
/api/users/0/items/{key}              → Single item
/api/users/0/items/{key}/children     → Child items (notes, attachments)
/api/users/0/items/{key}/file         → Attachment file (302 redirect)
/api/users/0/items/{key}/file/view/url → Attachment file path (returns plain text)
/api/users/0/items/{key}/fulltext     → Full-text index content (new in Zotero 8)
/api/users/0/items/{key}/tags         → Item tags

/api/users/0/collections              → All collections
/api/users/0/collections/top          → Top-level collections
/api/users/0/collections/{key}        → Single collection
/api/users/0/collections/{key}/items  → Items in a collection

/api/users/0/searches                 → Saved searches
/api/users/0/searches/{key}/items     → Execute search and return results (not possible with Web API)

/api/users/0/tags                     → All tags

/api/users/0/fulltext                 → Full-text version tracking (Zotero 8)

/api/users/0/groups                   → Groups the user belongs to
/api/groups/{id}/...                  → Group data (same structure as above)
```

**Query parameters**: `format` (json/bibtex/csljson/ris/... 14 formats total), `include`, `style`, `q` (search), `qmode`, `itemType`, `tag`, `sort`, `direction`, `limit`, `start`, `since`, `includeTrashed`

**Read/write capabilities**:

| Capability | Status |
|------|------|
| Read items, collections, tags | ✅ Full |
| Execute saved searches | ✅ (not possible with Web API) |
| Get attachment file path | ✅ |
| Get full-text index content | ✅ (Zotero 8) |
| Multi-format export | ✅ 14 formats |
| Write (create/modify/delete) | ❌ Not yet implemented |

**Authentication**: No authentication required; security is ensured by localhost binding.

**Limitations**:
- Read-only (as of 8.0.3, write support is still not available; the team states it "may be tricky to make fully compatible")
- Requires the Zotero desktop client to be running
- Requires the user to manually enable it in settings
- No official standalone documentation page (information is scattered across the zotero-dev mailing list and source code)

---

### 2.2 Direct SQLite Read Access

**Overview**: Zotero stores all metadata in a SQLite database file, which external applications can read directly.

**Database location**:

| Platform | Path |
|------|------|
| macOS | `/Users/<username>/Zotero/zotero.sqlite` |
| Windows | `C:\Users\<username>\Zotero\zotero.sqlite` |
| Linux | `~/Zotero/zotero.sqlite` |

(The actual path can be confirmed via "Show Data Directory" in Zotero settings.)

**Attachment storage**: Located under the `<data_dir>/storage/<8-character-ID>/` directory, e.g., `storage/N7SMB24A/document.pdf`.

**Available versions**: Zotero 7, Zotero 8 (schema versions may have migration changes between versions, with no official documentation).

**Read/write capabilities**:

| Capability | Status |
|------|------|
| Read all metadata | ✅ Open in read-only mode |
| Write | ❌ **Officially explicitly prohibited** — writing while Zotero is running will corrupt the database; writing while Zotero is not running bypasses data validation and referential integrity checks |

**Concurrent read access**:
- While Zotero is running, the database can be opened in SQLite read-only mode (`?mode=ro` / `SQLITE_OPEN_READONLY`)
- The journal mode used internally by Zotero (WAL or DELETE) is not officially documented; run `PRAGMA journal_mode;` to confirm
- SQLite lock contention may be encountered; retry logic should be implemented

**Other files in the data directory**:
```
zotero.sqlite.bak          → Automatic backup (every 12 hours)
zotero.sqlite.[N].bak      → Version upgrade backup
storage/                   → PDF and other attachment files
translators/               → Import/export translators
styles/                    → Citation style files
```

**Limitations**:
- Schema has no official public documentation and may change between versions
- There is a schema migration from 7→8; downgrading will cause errors
- Does not include sync status information

---

### 2.3 Plugin System

**Overview**: Zotero plugins are `.xpi` files that run inside the Zotero desktop client with full JavaScript API access. This is the only native local solution for full read/write access provided by Zotero.

**Available versions**: Zotero 7 (bootstrapped extension), Zotero 8 (same architecture, JSM→ESM migration).

**Plugin structure**:
```
my-plugin.xpi (ZIP)
├── manifest.json           → WebExtension-style manifest
├── bootstrap.js            → Lifecycle hooks
├── content/
│   ├── preferences.xhtml   → Settings panel
│   └── ...
└── locale/                 → Internationalization
```

**Lifecycle hooks** (`bootstrap.js`):
```javascript
function startup({ id, version, rootURI }) { ... }
function shutdown() { ... }
function install() { ... }
function uninstall() { ... }
function onMainWindowLoad({ window }) { ... }    // Main window loaded
function onMainWindowUnload({ window }) { ... }  // Main window unloaded
```

**3.A — JavaScript API Access**

Plugins have full access to all internal APIs of the `Zotero` object:

```javascript
// Read items
let item = await Zotero.Items.getAsync(itemID);
let title = item.getField('title');
let abstract = item.getField('abstractNote');

// Read attachments
let attachments = item.getAttachments();
let attachment = await Zotero.Items.getAsync(attachments[0]);
let filePath = await attachment.getFilePathAsync();

// Read notes
let notes = item.getNotes();

// Create/modify items
item.setField('extra', 'PRAG analyzed');
await item.saveTx();

// Search
let search = new Zotero.Search();
search.addCondition('title', 'contains', 'transformer');
let results = await search.search();

// Get collection contents
let collection = await Zotero.Collections.getAsync(collectionID);
let childItems = collection.getChildItems();

// File I/O
let content = await Zotero.File.getContentsAsync(path);
await Zotero.File.putContentsAsync(path, data);

// Generate bibliography
let biblio = Zotero.QuickCopy.getContentFromItems(items, format);
```

**3.B — Custom HTTP Endpoints**

Plugins can register custom endpoints on the `:23119` server:

```javascript
// Register endpoint
Zotero.Server.Endpoints["/prag/search"] = function() {};
Zotero.Server.Endpoints["/prag/search"].prototype = {
    supportedMethods: ["GET", "POST"],
    supportedDataTypes: ["application/json"],
    init: async function(options) {
        // options.data contains the request data
        // Returns [statusCode, contentType, responseBody]
        return [200, "application/json", JSON.stringify({ results: [...] })];
    }
};
```

This is a native Zotero mechanism — `Zotero.Server.Endpoints` is the built-in HTTP server extension point provided by Zotero.

**3.C — Data Change Notifications (Notifier)**

```javascript
let observerID = Zotero.Notifier.registerObserver({
    notify: function(event, type, ids, extraData) {
        // event: 'add', 'modify', 'delete', 'move', 'remove', 'trash', ...
        // type: 'item', 'collection', 'tag', 'collection-item', ...
        // ids: Array of IDs of affected objects
    }
}, ['item', 'collection'], 'prag-observer');

// Cleanup
Zotero.Notifier.unregisterObserver(observerID);
```

**Listenable event types**: add, modify, delete, move, remove, refresh, redraw, trash, unreadCountUpdated, index, open, close, select

**Listenable object types**: collection, search, item, file, collection-item, item-tag, tag, setting, group, trash, relation, feed, feedItem, sync, api-key, tab, itemtree, itempane

**3.D — Stable Registration-based APIs (Zotero 7+, version stability commitment in 8)**

| API | Purpose | Version |
|-----|------|------|
| `Zotero.ItemTreeManager.registerColumn()` | Custom list columns | 7+ |
| `Zotero.ItemPaneManager.registerSection()` | Custom item detail panel sections | 7+ |
| `Zotero.ItemPaneManager.registerInfoRow()` | Custom item info rows | 7+ |
| `Zotero.Reader.registerEventListener()` | PDF reader event hooks | 7+ |
| `Zotero.PreferencePanes.register()` | Custom settings panels | 7+ |
| **`Zotero.MenuManager.registerMenu()`** | **Custom context menus** | **8+** |
| `Zotero.Server.Endpoints[]` | Custom HTTP endpoints | 7+ |
| `Zotero.Notifier.registerObserver()` | Data change notifications | 7+ |

**Breaking changes from 7→8**:
- JSM → ES Modules (`ChromeUtils.import()` → `import`)
- Bluebird → Standard Promise
- `Zotero.spawn()` removed
- Settings panels run in an isolated global scope
- Migration scripts provided: `migrate-fx140/migrate.py esmify` and `asyncify`

**Limitations**:
- Requires developing and distributing an XPI plugin
- Internal JS API documentation is incomplete ("not comprehensive"); source code reference is needed
- Version upgrades may introduce breaking changes (7→8 had significant impact; post-8, greater stability is promised)
- JavaScript-only development

---

### 2.4 Connector HTTP Server

**Overview**: An HTTP server running on port 23119 within the Zotero desktop client, through which the browser Connector extension communicates with Zotero. The Local API (`/api/...`) also runs on the same port.

**Available versions**: Zotero 7, Zotero 8 (`/connector/savePage` was removed in 8).

**Endpoints**:

| Endpoint | Method | Purpose | Zotero 8 |
|------|------|------|----------|
| `/connector/ping` | GET | Detect whether Zotero is running; returns version info | ✅ |
| `/connector/saveItems` | POST | Save items to Zotero (with metadata) | ✅ |
| `/connector/saveSnapshot` | POST | Save a web page snapshot | ✅ |
| `/connector/selectItems` | POST | Pop up an item selection dialog | ✅ |
| `/connector/getTranslatorCode` | POST | Get translator code | ✅ |
| `/connector/savePage` | POST | Save a web page | ❌ **Removed** |

**Read/write capabilities**:
- Read: Limited (ping, translator code)
- Write: Can save new items and snapshots to Zotero

**Authentication**: None. Cross-origin restrictions prevent browsers from reading responses, but curl/programmatic access works normally.

**Limitations**:
- Extremely narrow functionality, designed specifically for the browser → Zotero save scenario
- Cannot query, search, or export library data
- Official documentation may lag behind ("not always up-to-date"); it is recommended to refer to the source code `server_connector.js`

---

### 2.5 Web API v3 (Remote REST API)

**Overview**: A RESTful API at `https://api.zotero.org` providing full read/write access to cloud-hosted Zotero libraries.

**Available versions**: Independent of desktop version; available for both Zotero 7 and 8. No major changes to the Web API itself between 7 and 8.

**Read/write capabilities**: Full read/write.

**Authentication**:
- API Key (created at zotero.org/settings/keys), passed via `Zotero-API-Key` header or Bearer token
- OAuth 1.0a (for third-party application authorization flows)
- Permission scopes: library_access, notes_access, write_access, all_groups

**Key capabilities**:
- Item CRUD, batch operations (up to 50 items/request)
- Collections, Tags, Saved Searches management
- Full-text content storage and retrieval
- File upload/download (supports incremental upload)
- 14 export formats
- Version conflict detection (optimistic locking, `If-Unmodified-Since-Version`)

**Limitations**:
- Requires network connectivity
- Rate limiting (429 response + Retry-After header)
- Pagination maximum of 100 items/request
- Bibliography format limited to 150 items
- Saved Searches can only retrieve definitions, **cannot execute searches** (Local API can)
- File storage quota (300MB free)

---

### 2.6 Export/Import Translators

**Overview**: Zotero's built-in translator system, supporting import and export of multiple academic data formats.

**Available versions**: Zotero 7, Zotero 8 (architecture unchanged; the Scaffold development tool has improvements in 8).

**Supported formats**:

| Format | API Parameter | Import | Export |
|------|---------|------|------|
| BibTeX | `bibtex` | ✅ | ✅ |
| BibLaTeX | `biblatex` | ✅ | ✅ |
| CSL-JSON | `csljson` | ✅ | ✅ |
| RIS | `ris` | ✅ | ✅ |
| Zotero RDF | `rdf_zotero` | ✅ | ✅ |
| MODS | `mods` | — | ✅ |
| TEI | `tei` | — | ✅ |
| CSV | `csv` | — | ✅ |
| Dublin Core RDF | `rdf_dc` | — | ✅ |
| COinS | `coins` | — | ✅ |
| Wikipedia | `wikipedia` | — | ✅ |
| Bookmarks | `bookmarks` | — | ✅ |

**How to trigger**:
- Local API: `GET /api/users/0/items?format=bibtex`
- Web API: `GET /users/{id}/items?format=csljson`
- Desktop menu: File → Export Library / Export Items

**Limitations**:
- API export is limited to items (cannot export collections/tags individually)
- `bib` format limited to 150 items
- Custom translators require JavaScript development + Scaffold tool

---

### 2.7 `zotero://` URI Scheme (Deep Links)

**Overview**: A protocol handler registered by Zotero that can activate Zotero and navigate to a specific item via a URI.

**Available versions**: Zotero 7, Zotero 8 (URI parsing has slight changes in 8 — "first segment is now parsed as host").

**URI format**:
```
zotero://select/library/items/{ITEMKEY}              → Personal library item
zotero://select/groups/{GROUPID}/items/{ITEMKEY}     → Group library item
zotero://select/library/collections/{COLLKEY}        → Collection
```

**Behavior**: Clicking or opening a URI → activates Zotero → selects the target item in the library.

**Limitations**:
- Navigation/activation functionality only; does not return data
- When Zotero is not running, the first invocation may only launch the application without selecting the item (requires a second invocation)
- Cannot be used for programmatic data access

---

## 3. PRAG Integration Scenario Mapping

| PRAG Requirement | Recommended Method | Alternative Method | Notes |
|-----------|---------|---------|------|
| **Read paper metadata** | Local API | Direct SQLite read | Local API preferred; use SQLite when Zotero is not running |
| **Get PDF file path** | Local API (`/file/view/url`) | SQLite + storage directory mapping | Local API directly returns the physical file path |
| **Search papers** | Local API (`?q=` or saved search) | SQLite query | Unique Local API advantage: can execute saved searches |
| **Filter by collection** | Local API (`/collections/{key}/items`) | SQLite join | — |
| **Get full-text index** | Local API (`/fulltext`, Zotero 8) | Direct SQLite read | New endpoint in Zotero 8 |
| **Real-time awareness of paper changes** | Plugin (Notifier) | Poll Local API | Notifier is event-driven and more efficient |
| **Trigger PRAG from within Zotero** | Plugin (custom endpoint + context menu) | — | Register `/prag/ask` endpoint + MenuManager |
| **Write tags/notes back to Zotero** | Plugin (JS API) | Web API (requires network) | Local writing is only possible via the Plugin approach |
| **Jump from PRAG to a Zotero item** | `zotero://` URI | — | Embed deep links in the PRAG interface |
| **Export to standard formats** | Local API (`?format=csljson`) | Export Translators | 14 formats available |
| **Detect whether Zotero is running** | Connector (`/connector/ping`) | Try connecting to Local API | — |

---

## 4. Integration Complexity Levels

### Level 0 — Zero-plugin Integration (Simplest, Read-only)

```
PRAG ──HTTP GET──► Zotero Local API (:23119/api/)
PRAG ──SQLite────► ~/Zotero/zotero.sqlite (read-only, fallback)
PRAG ──zotero://──► Zotero UI (deep links)
```

- No Zotero plugin development required
- Full read access to paper metadata, attachment paths, full-text index
- Cannot trigger PRAG from within Zotero, cannot write data back
- **Suitable for the MVP stage**

### Level 1 — Lightweight Plugin (Enhanced Reading + Basic Interaction)

Building on Level 0, add an approximately 50KB Zotero plugin:

```
Zotero Plugin:
  ├── Register context menu "Ask PRAG" (MenuManager, Zotero 8)
  ├── Register custom endpoint /prag/selected-items (Server.Endpoints)
  ├── Subscribe to item add/modify events (Notifier)
  └── Display PRAG summary in item detail panel (ItemPaneManager)

PRAG:
  ├── Listen for requests sent by the plugin via HTTP
  └── Read complete data via Local API
```

- Users can right-click "Ask PRAG" from within Zotero
- PRAG has real-time awareness of library changes
- Still does not write data back to Zotero
- **Suitable for Phase 2**

### Level 2 — Full Integration (Bidirectional Sync)

Building on Level 1, add write capabilities:

```
Zotero Plugin:
  ├── All Level 1 functionality
  ├── Expose write endpoint /prag/write-back (Server.Endpoints)
  │   ├── Add tags
  │   ├── Add notes
  │   └── Add relations
  └── Internally call Zotero JS API to perform writes

PRAG:
  ├── Call plugin write endpoint after analysis is complete
  └── Write analysis tags, summary notes, etc. back to Zotero
```

- PRAG analysis results can be written back to Zotero (tags, notes, relations)
- Requires more plugin development effort
- Must handle Zotero 7/8 API compatibility
- **Suitable for Phase 3+**

---

## 5. Key Findings and Recommendations

### Findings

1. **Local API is more powerful than expected**: Supports executing saved searches (which the Web API cannot do), directly obtaining file paths, 14 export formats, and full-text indexing (Zotero 8). For read scenarios, it fully meets PRAG's needs.

2. **Local API read-only is a hard limitation**: As of Zotero 8.0.3, write support is still not implemented. The Zotero team has stated they plan to add it but it "may be tricky." If PRAG needs to write data back, **the plugin route is mandatory**.

3. **Plugins are the only local write channel**: There is no non-plugin way to safely write data to Zotero locally. Direct SQLite writes are explicitly prohibited by the official team. The Connector HTTP can only save new items (cannot modify existing items).

4. **Plugin development cost is manageable**: All plugin features needed by PRAG (context menus, custom endpoints, Notifier, panel sections) have stable registration-based APIs and do not require hacking internal implementations. Zotero 8 promises cross-version stability.

5. **SQLite is a valuable supplement**: When Zotero is not running (e.g., PRAG starts before Zotero after a system boot), direct SQLite reading is the only way to access data.

6. **`zotero://` URIs provide free UX enhancement**: Embedding `zotero://select/...` links in PRAG responses allows users to jump to the original item in Zotero with one click, at zero development cost.

### Recommendations

- **Do not develop a Zotero plugin during the MVP stage**; use only Local API + direct SQLite reading for one-way read access
- **Postpone plugin development until the core RAG pipeline has been validated**
- **Prioritize Zotero 8 support** (richer API, stronger stability commitment); target Zotero 7 as a compatibility goal
- **Embed `zotero://` deep links in PRAG responses** for zero-cost UX improvement
