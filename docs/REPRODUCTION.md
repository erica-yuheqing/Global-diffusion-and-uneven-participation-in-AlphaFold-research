# Reviewer reproduction paths

From the installed repository, choose a fresh output path for each command. Output paths in the examples are relative to the current directory.

| Topic | Command | Required data bundles (stems) | What it verifies |
|---|---|---|---|
| All graphics | `python reproduce.py redraw Fig01 --output ../review/Fig01` (substitute any figure ID) | 01_figures_and_display_tables | Recreates figure from the published figure inputs. |
| All supplementary tables | `python tools/export_tables.py --output ../review/table-text` | 01_figures_and_display_tables | Recreates 14 readable Markdown tables from display-level CSVs. Source index points to analysis-level files. |
| National concentration | `python tools/replay_methods.py national --output ../review/national` | analysis_01_national | Reconstructs national point statistics. Original matched summaries are fixed. A local alternative draw sequence is separately identified in historical_draw_audit. |
| Institutional coverage | `python tools/replay_methods.py coverage --output ../review/coverage` | analysis_02_coverage | Rebuilds cohort and coverage summaries and checks opportunity expectations. |
| Follow-up and continuity | `python tools/replay_methods.py continuity --output ../review/continuity` | analysis_03_continuity | Rebuilds nine source tables and tests identifier/group linkage. |
| Authorship normalization | `python tools/rebuild_authors.py --output ../review/authors` | 03_author_input_shards, analysis_04_authorship | Runs the historical N01 preparation and compares ten normalized Parquet relations in both directions, including row multiplicities. |
| Authorship method fixtures | `python tools/replay_methods.py authorship --output ../review/authorship-tests` | analysis_04_authorship | Checks study credits, support and related method invariants. A C++17 compiler is needed to build the optional historical endpoint engine. |
| Income sensitivities | `python tools/replay_income.py --output ../review/income` | analysis_04_authorship, analysis_06_income | Reaggregates common bootstrap credits and coverage by the frozen World Bank groups; compares 11 tables. |
| Extended Data 8 intervals | `python tools/replay_methods.py ed8-bootstrap --output ../review/ed8` | 01_figures_and_display_tables, analysis_04_authorship | Regenerates the two sets of 2,000 group-matrix draws. |
| Citations | `python tools/replay_methods.py citations --output ../review/citations` | analysis_05_outcomes_networks | Recomputes mature-window counts and percentile ranks from the deposited incoming edges. |
| Main results | `python tools/check_main_results.py --output ../review/main_results.json` | 01_figures_and_display_tables, 02_corpus_and_decisions, analysis_05_outcomes_networks | Checks denominators, annual AF counts, within-institution matched estimates in Fig. 5 and regression slopes in Fig. 6. |
| Historical journal ranking | `python tools/rebuild_journals.py --ranking-dir ../ranking --output ../review/journals` | 04_source_metadata and 11 separately acquired annual CSV files | Reconstructs historical category/source-year rankings with the manuscript’s annual ISSN and tie rules. |
| Optional full M8 numerical workflow | `python tools/rebuild_outcomes.py --output ../review/full-m8` | analysis_05_outcomes_networks | Starts from an empty cache, advancing from citation metrics to rosters, matching, networks, outcomes, strata, regressions and data tables. Use `--through metrics` for the short entry point. |

The source data sit beside the matching analysis code in analysis_archives. Some original scripts address the historical project layout and private evidence workspaces. Use the portable entry points above for reviewing the public deposit. Historic figure numbers such as “Fig6” in M8 scripts can predate final manuscript numbering; use the figure index and the panel crosswalk for final numbering.

## What can be recovered

The M2 original published Monte Carlo matching summaries and endpoints are preserved. The original seed and exact draw sequence were absent from the collaborators’ handoff. The separate local matching audit used seed 20261025 and gives slightly different Monte Carlo means. Its draws must not be substituted for the manuscript series. Most method modules include historical reference draws. The release reran the recorded checks and ED8 bootstrap; the entire set of historical allocation, endpoint and adjusted-model simulations has not been independently replayed in this packaging run.

Raw evidence and provider outputs are outside the deposit. Reacquisition may change upstream records, model versions, prices and availability. The frozen human/model decisions and reviewed study crosswalk provide the common starting point for checking the reported numbers.
