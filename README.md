# Global diffusion and uneven participation in AlphaFold research

Reproducibility code for the November 19, 2026 manuscript freeze. The **figure bundle alone** reproduces all 6 main figures, 10 Extended Data figures, 19 supplementary figures and the 40 displayed blocks of Supplementary Tables S1–S14. The larger bundles support checking how the plotted values were derived.

**Network analyses.** The country-level network figures, five-joint-publication edge filter and country shortest-path centrality calculations in the historical notebooks are retired. To reproduce the manuscript’s institutional collaboration results, follow the [M7 and M8 implementations](docs/REPRODUCTION.md#institutional-collaboration-in-m7-and-m8).

## Desktop requirements and installation

The reviewer demos were tested on macOS 26.4.1 (25E253, arm64), on an Apple M2 Max with 32 GiB RAM, using CPython 3.11.11, pip 24.0 and Poppler 25.06.0. An ordinary CPU computer is sufficient. These demos require no GPU acceleration, cluster, credentials or paid services. The tested configuration is a reference machine, not a minimum RAM requirement. The commands assume a POSIX shell. Linux has not been verified with this checklist, and Windows has not been tested.

Install Python 3.11 and Poppler first. On macOS with Homebrew, run `brew install python@3.11 poppler`. Verify that `python3.11 --version`, `pdfinfo -v` and `pdftoppm -v` work. The [Python dependencies](requirements.txt) include the tested versions. The optional historical endpoint rebuild additionally uses a C++17 compiler.

## Start with one figure

Download [the figure and table demo ZIP (12.75 MB)](https://zenodo.org/records/24369846/files/01_figures_and_display_tables.zip?download=1) into a folder named `zenodo` beside the code repository. Leave the ZIP intact. Run the following commands from the repository root. Other [Zenodo bundles](https://doi.org/10.5281/zenodo.24369846) are only needed for the additional analyses.

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

**Expected result and time.** The Figure 1 command writes `../review/Fig01/figures/Figure1_concentration_refined.pdf` (one page) and `../review/Fig01/run_report.json` with `"status": "passed"`. In one fresh desktop trial, environment creation took 2.08 s, installing the pinned packages took 30.92 s with the pip cache disabled, and verifying and unpacking the demo took 0.23 s. Allow about **33 s for installation** with Python and Poppler already available. The demo ZIP download took an additional 27.36 s. Figure 1 took **about 40 s** after installation. Package and data download times depend on the connection and package mirror. [Measured run](verification/desktop_demo.json)

The CLI accepts Fig01–Fig06, ED01–ED10 and S01–S19. Each redraw requires a new output directory. It creates a fresh working copy, runs the figure script and records output PDF paths, elapsed time and checks in run_report.json. For every figure in one run:

```sh
python -c "import json,subprocess,sys; items=json.load(open('manifests/figure_index.json')); [subprocess.run([sys.executable,'reproduce.py','redraw',i['id'],'--output','../review-all/'+i['id']],check=True) for i in items]"
```

## Use your own country-year data

The national concentration calculation accepts a UTF-8 CSV. Start with the [six-row worked example](examples/country_credits.csv). Supply one row per country and calendar year with these columns:

| Column | Meaning |
|---|---|
| `year` | Integer calendar year. |
| `country_code` | Nonempty identifier, unique within year. Use the same roster every year. |
| `af_credit` | Known, non-negative AF study credit for that country and year. Fractional credits are allowed. Include known zeros explicitly. Resolve or document missing data before running. Each annual total must be positive. |

```sh
python tools/check_national_points.py --credits-csv examples/country_credits.csv
python tools/check_national_points.py --credits-csv /path/to/your_country_credits.csv
```

The command prints annual Gini, Herfindahl–Hirschman index (HHI) and top-five and top-ten shares as JSON. In the example the credits are 0, 1 and 3 in 2024, giving a Gini of 0.5 and HHI of 0.625. All three countries have equal credit in 2025, giving a Gini of 0 and HHI of 1/3. Both top shares are 1 in each year because the roster contains only three countries. The example took about 0.5 s and requires only the code and Python environment. It calculates point estimates. The Figure 1 redraw above uses the deposited manuscript inputs, including reference estimates and intervals.

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
