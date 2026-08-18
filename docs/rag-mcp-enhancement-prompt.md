Enhance the `query_documents` (and similarly-shaped) tools in this MCP
server to return structured, minimal output instead of one large
pre-formatted text blob. Currently each call joins all hits into a single
string with "Rank N" / "---" separators and repeats full YAML frontmatter
(title, url, tags, created/updated/published) inline with the chunk text
for every hit — even when multiple hits come from the same source
document. This is protocol-level (MCP content-block shape), not specific
to any one client, so fixing it helps every MCP host that calls this
server.

Make these changes:

1. Return one content item per hit (or a single structured JSON array),
   not one joined string. Let the hits be a list in the response rather
   than pre-rendered prose.

2. Separate chunk content from metadata. Metadata (title, url, tags,
   created/updated/published, source path, chunk_index, content_hash)
   should be a sibling field per hit, not text baked into the chunk
   string.

3. Dedupe frontmatter across chunks from the same source file. If
   multiple ranked hits come from the same document, don't repeat the
   full frontmatter block for each one — reference the source path once.

4. Add a verbosity/format parameter to the tool schema (e.g.
   `compact: bool` or `fields: [...]`) so callers can request a lean
   response (just content + distance) by default, with full metadata
   available opt-in.

5. Trim incidental noise: cap distance score precision (e.g. 3 decimal
   places), and keep default `n_results` reasonable so the combination
   of hit count × repeated metadata doesn't balloon response size.

Goal: smaller, structured responses that any MCP client can render
sensibly, and that don't dump as a wall of raw text when a client falls
back to default JSON rendering.
