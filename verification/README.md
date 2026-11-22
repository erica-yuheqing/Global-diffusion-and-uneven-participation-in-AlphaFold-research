# Checks performed for this release

- Five final manuscript DOCX files were fingerprinted; their 35 figure media objects matched the handoff. The final manuscript names and hashes are in [document_freeze.csv](document_freeze.csv).
- All 35 primary PDFs were drawn from figure data in fresh directories under a separately installed CPython 3.11 environment. All have the reference page dimensions at the 96 dpi raster comparison. Differences in rendering are recorded per figure; five comparison rasters match pixel-for-pixel. The mean absolute RGB difference is at most 2.5573 on the 0–255 scale. [Execution results](redraws.json) · [Raster comparisons](render_comparison.csv)
- All 14 supplementary tables are indexed. Of 40 display blocks, 26 matched native Word tables cell by cell after whitespace/dash normalization. For 14 blocks on embedded image pages, body rows were compared to decoded vector glyphs. These comparisons check displayed values at manuscript precision. They do not reproduce editorial line wrapping, all rendered headings or table notes. [Table-by-table results](table_checks.csv)
- The [51 numerical checks](main_results.json) cover cohort denominators, AF annual counts, within-institution matched outcome estimates and regression slopes. For authorship, [10 bidirectional multiset comparisons](authorship_normalization.json) had zero differences after independent normalization from the recovered 77 source files.
- Additional offline runs replayed coverage and analytical expectations, follow-up linkage and nine tables, authorship fixtures, the ED8 bootstrap, eleven income-group tables, and fixed-window citation counts and percentiles. All 2,714,594 main-period studies were processed in the citation replay. [Historical journal input reconstruction](journal_reconstruction.json) compares the recreated ranking inputs to the private originals.
- The M2 published composition-matching summaries are reproducible at figure level; the exact original draw sequence is unavailable. Recorded 5,000-draw results are supplied where applicable. Full refitting of all historical simulations and cross-platform execution are outside this release’s verification run.

See [reviewer commands](../docs/REPRODUCTION.md) and [source-to-method mapping](../manifests/manuscript_crosswalk.csv).

The [installation audit](installation.json) records file counts and archive coverage for a fresh, offline installation. The [M8 source inventory](outcomes_input_recovery.csv) covers all 14 previously referenced inputs, including the two reconstructed separately. The endpoint C++17 implementation was compiled and loaded on macOS in this release check.


## Desktop demo and user-supplied data

On 22 November 2026 we downloaded the code and figure bundle, created a fresh Python environment and timed dependency installation, archive verification and the Figure 1 redraw. A six-row synthetic CSV exercised the same national concentration calculation on user-supplied inputs. Its two annual results agreed with hand calculations. The CSV entry point also matched all four saved national point estimates for each of the five reference years (2021–2025). The paper's frozen comparison uses 227 countries. [Machine, timings and numerical results](desktop_demo.json) · [Commands and expected output](../README.md#start-with-one-figure)

This was an author-side automated check. An independent colleague's installation and feedback remain pending. The five document fingerprints above refer to the original 19 November manuscript freeze, before its availability links were updated.
