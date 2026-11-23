# Writing for scgraph

Read this page before you write a docstring, a document, an issue or a PR.

The reader is a developer whose first language is not English. This reader looks for a
heading, a code block or a table, and reads each sentence once.

## Rules

1. **Subject, verb, object.** One idea in a sentence of about 20 words.
2. **Common verbs with one meaning.** Write "use", not "fall back to". Write "create", not
   "set up". Write "an edge gets a weight", not "an edge pays a weight".
3. **The verb, not a noun made from it.** Write "`read` checks the header", not "the check of
   the header on a read".
4. **One word for one thing.** Use the words of `ARCHITECTURE.md`. Do not invent a word.
5. **The form that fits.** Cases go in a table, steps in a list, a value in a code block.
6. **Terms first.** A table or a code block may come first, if the sentence before it defines
   its new terms.
7. **Do not pack.** Three facts need three sentences, or three rows of a table.

## Examples

| Kind | Do not write | Write |
|---|---|---|
| Sentence | The weights are lined up with the edges. | The array has one weight for each edge, by edge id. |
| Sentence | scgraph falls back to pure Python. | scgraph uses its pure-Python code when the C++ extension is not installed. |
| Sentence | Downloads nothing; `FileNotFoundError` if not cached. | The call downloads nothing. It raises `FileNotFoundError` when the cache does not hold the network. |
| Opening of a guide | This guide is for a user who needs a network. After it, you can load… | This guide shows three ways to get a network: load one, build one, or load your own data. |
| Heading in `ARCHITECTURE.md` | The Checks of a Read | Validation on Read |
| Heading in a guide | The Same Network Later | Loading the Same Network Again |
| Name | `_internal.py`, `columns.py` | `deprecations.py`, `array_views.py` |
| Name | `offsets`, `heads` | `node_first_edge_ids`, `edge_destination_node_ids` |

## Cases Go in a Table

Do not write:

> The first call downloads the sources and builds the network, which is then kept in the
> cache, so that a later call loads it without any network access; a network built by
> another version of its pipeline is built again.

Write a table, with the same structure in each column:

| Case | What `build_geograph` does |
|---|---|
| First call | Downloads the sources, builds the network, and keeps the file in the cache |
| Later call | Loads the file from the cache, without network access |
| The pipeline changed in an upgrade | Builds the network again |
