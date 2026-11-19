# Global diffusion and uneven participation in AlphaFold research

Reproducibility code for the November 19, 2026 manuscript freeze. The **figure bundle alone** reproduces all 6 main figures, 10 Extended Data figures, 19 supplementary figures and the 40 displayed blocks of Supplementary Tables S1–S14. The larger bundles support checking how the plotted values were derived.

## Start with one figure

Use Python 3.11 on macOS or Linux. The tested environment used CPython 3.11.11 on Apple Silicon. Some rendering scripts also use the Poppler utilities (including pdftoppm and pdfinfo). The reference commands below assume this repository is the current directory and the downloaded Zenodo files are in a sibling directory named zenodo.

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python reproduce.py verify
python tools/install_data.py --from-dir ../zenodo --bundle 01_figures_and_display_tables
python reproduce.py list
python reproduce.py redraw Fig01 --output ../review/Fig01
python tools/export_tables.py --output ../review/tables
```

The CLI accepts Fig01–Fig06, ED01–ED10 and S01–S19. Each redraw requires a new output directory. It creates a fresh working copy, runs the figure script and records output PDF paths, elapsed time and checks in run_report.json. For every figure in one run:

```sh
python -c "import json,subprocess,sys; items=json.load(open('manifests/figure_index.json')); [subprocess.run([sys.executable,'reproduce.py','redraw',i['id'],'--output','../review-all/'+i['id']],check=True) for i in items]"
```

## Verify the analyses

Install the ten Zenodo ZIPs for the complete review workspace:

```sh
python tools/install_data.py --from-dir ../zenodo
```

The installer verifies the archive and each installed member with SHA-256, and can safely be rerun after interruption. Data are overlaid beside the corresponding code. Reserve at least the sum of the downloaded and unpacked sizes plus working space for your chosen analyses. Record-level normalization and full simulation reruns require more temporary disk space than a figure redraw.

- [Numerical checks and optional rebuilds](docs/REPRODUCTION.md)
- [Data acquisition, corpus construction and study definitions](docs/DATA_PROCESSING.md)
- [Figure identifiers and scripts](manifests/figure_index.json) · [Panel-level caption crosswalk](manifests/panel_crosswalk.csv)
- [Methods, figures and upstream analysis modules](manifests/manuscript_crosswalk.csv) · [Unrounded supplementary table sources](manifests/table_source_index.json) · [Displayed table cells](manifests/table_display_index.json)
- [Verification evidence](verification/README.md) · [Third-party sources](THIRD_PARTY.md) · [Code license](LICENSE)

The repository and the dataset are separate release artifacts. Python scripts under pipeline preserve the original acquisition and evidence workflow. The portable reviewer entry points use the deposited analytical inputs and require zero provider calls. The authorship and reconstruction helpers use POSIX filesystem features. No Windows execution was tested.

For the submission statement and software citation, see [availability wording](docs/AVAILABILITY.md) and [citation metadata](CITATION.cff).
