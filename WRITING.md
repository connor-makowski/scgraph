# Writing for scgraph

Read this page before you write a docstring, a document, an issue or a pull request.

The reader is a developer whose first language is not English. This reader looks for a
heading, a code block or a table, and reads a sentence only once.

## Rules

1. **Subject, verb, object.** One idea in a sentence, in about 20 words.
2. **Common verbs with one meaning.** No phrasal verb ("set up", "fall back"). No verb used
   as an image ("an edge pays", "a node lives").
3. **A verb, not an abstract noun.** Write "`read` checks the header", not "the check of
   the header on a read".
4. **One word for one thing.** Use the words of `ARCHITECTURE.md`. Do not invent a word.
5. **The form that fits.** Cases go in a table, steps in a list, a value in a code block.
6. **Do not pack.** Three facts need three sentences, or three rows of a table.

## Examples

| Kind | Do not write | Write |
|---|---|---|
| Sentence | The weights are lined up with the edges. | The array has one weight for each edge, by edge id. |
| Sentence | An edge without a class pays the weight of `off_graph`. | An edge without a class gets the weight per km of `off_graph`. |
| Sentence | scgraph falls back to pure Python. | scgraph uses its pure-Python code when the C++ extension is not installed. |
| Sentence | Downloads nothing; `FileNotFoundError` if not cached. | The call downloads nothing. It raises `FileNotFoundError` when the cache does not hold the network. |
| Opening of a guide | This guide is for a user who needs a network. After it, you can load… | This guide shows three ways to get a network: load one, build one, or load your own data. |
| Heading in `ARCHITECTURE.md` | The Checks of a Read | Validation on Read |
| Heading in a guide | The Same Network Later | Loading a Recorded Network Release |
| Name | `_internal.py`, `columns.py` | `deprecations.py`, `array_views.py` |
| Name | `offsets`, `heads` | `node_first_edge_ids`, `edge_destination_node_ids` |

## Cases Go in a Table

Do not write:

> The first call downloads the sources and builds the network, which is then kept in the
> cache, so that a later call loads it without any network access; a network built by
> another version of its pipeline is built again.

Write a table. Each cell of a column has the same structure:

| Case | What `build_geograph` does |
|---|---|
| First call | Downloads the sources, builds the network, and keeps the file in the cache |
| Later call | Loads the file from the cache, without network access |
| The pipeline changed in an upgrade | Builds the network again |
