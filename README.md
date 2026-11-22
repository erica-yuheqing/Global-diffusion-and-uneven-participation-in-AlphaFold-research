# Global diffusion and uneven participation in AlphaFold research

This repository contains the code accompanying *Global diffusion and uneven participation in AlphaFold research*. It includes workflows for identifying research use of AlphaFold, examining participation across countries and institutions, and analysing authorship, collaboration and publication outcomes.

The accompanying datasets are available on [Zenodo](https://doi.org/10.5281/zenodo.24369846). To regenerate the manuscript figures and supplementary tables from saved inputs, start with the figure and display-table bundle. Additional data bundles support the numerical analyses described in the [reproduction guide](docs/REPRODUCTION.md). The guide explains the required inputs, verification checks and remaining reproducibility limitations.

[Run Figure 1](#start-with-one-figure) · [Use your own CSV](#use-your-own-country-year-data) · [Verify the analyses](#verify-the-analyses)

## Desktop requirements and installation

| Platform | Test status |
| --- | --- |
| macOS | Tested on macOS 26.4.1 (25E253, arm64), Apple M2 Max, 32 GiB RAM. |
| Linux | The commands use a POSIX shell. The demos have not been verified on Linux. |
| Windows | Native Windows and WSL have not been tested. Some reconstruction tools require POSIX filesystem features. |

The demos run on a CPU and require no credentials. The tested software versions were CPython 3.11.11, pip 24.0 and Poppler 25.06.0. The repository includes [pinned Python dependencies](requirements.txt). The optional historical endpoint rebuild also requires a C++17 compiler.

**1. Install the prerequisites.** On macOS with Homebrew:

```sh
brew install python@3.11 poppler
python3.11 --version
pdfinfo -v
pdftoppm -v
```

**2. Set up the Python environment.** From the repository root:

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python reproduce.py verify
```

**Installation time:** about 33 seconds on the test machine with Python and Poppler already installed. This includes downloading the Python packages. The figure data are downloaded separately. [Timing record](verification/desktop_demo.json)

## Start with one figure

**Download the data.** Save the [figure and display-table ZIP (12.75 MB)](https://zenodo.org/records/24369846/files/01_figures_and_display_tables.zip?download=1) in a folder named `zenodo` beside the repository. Leave it zipped.

**Draw Figure 1.** With the environment above active, run:

```sh
python tools/install_data.py --from-dir ../zenodo --bundle 01_figures_and_display_tables
python reproduce.py redraw Fig01 --output ../review/Fig01
```

| What to check | Expected result |
| --- | --- |
| Figure | One-page PDF at `../review/Fig01/figures/Figure1_concentration_refined.pdf` |
| Run report | `../review/Fig01/run_report.json` contains `"status": "passed"` |
| Elapsed time | About 40 seconds for the redraw. The separate ZIP download took 27 seconds in the desktop trial. |

<details>
<summary><strong>Other figures and supplementary tables</strong></summary>

The same ZIP contains the plotting inputs for 6 main figures (`Fig01`–`Fig06`), 10 Extended Data figures (`ED01`–`ED10`) and 19 supplementary figures (`S01`–`S19`), plus the displayed values for Supplementary Tables S1–S14.

List the figure IDs or export the tables:

```sh
python reproduce.py list
python tools/export_tables.py --output ../review/tables
```

To redraw all 35 figures, run the following from the repository root. Use a fresh output directory for each figure. Each run creates a working copy and records the PDF path, elapsed time and checks in `run_report.json`.

```sh
python - <<'PYTHON'
import json
import subprocess
import sys
from pathlib import Path

figures = json.loads(Path("manifests/figure_index.json").read_text())
for figure in figures:
    figure_id = figure["id"]
    subprocess.run(
        [sys.executable, "reproduce.py", "redraw", figure_id,
         "--output", f"../review-all/{figure_id}"],
        check=True,
    )
PYTHON
```

</details>

## Use your own country-year data

The [six-row example CSV](examples/country_credits.csv) demonstrates how to calculate national concentration from one row per country and year. This example requires only the Python environment.

| CSV column | What to supply |
| --- | --- |
| `year` | Integer calendar year. |
| `country_code` | Nonempty identifier, unique within each year. Use the same roster every year. |
| `af_credit` | Known, non-negative AF study credit. Fractional values and explicit zeros are valid. The annual total must be positive. |

Use UTF-8 encoding. Resolve or document missing credits before running the calculation. Start with the example:

```sh
python tools/check_national_points.py --credits-csv examples/country_credits.csv
```

**Expected output.** The command prints annual Gini coefficients, Herfindahl–Hirschman indices (HHI) and top-five and top-ten shares as JSON. For 2024 and 2025, respectively, the example gives Gini values of **0.5 and 0** and HHI values of **0.625 and 1/3**. Both top shares are 1 in both years because the roster contains three countries. The example took about 0.5 seconds.

To calculate the same point estimates for your data, supply the path to your CSV:

```sh
python tools/check_national_points.py --credits-csv /path/to/your_country_credits.csv
```

## Verify the analyses

Use the [reproduction guide](docs/REPRODUCTION.md) to select an analysis, its data bundles and the command to run. To install the complete set, download all ten ZIPs into `../zenodo` and run:

```sh
python tools/install_data.py --from-dir ../zenodo
```

The installer verifies each archive and its files with SHA-256 and can resume after interruption. Allow space for the ZIPs, the extracted files and temporary working files. Record-level normalization and simulation reruns need more temporary space than figure redraws. The review commands use deposited inputs offline. The original acquisition and evidence-processing scripts are in [pipeline/](pipeline/).

| To find… | Open… |
| --- | --- |
| Corpus construction and inclusion rules | [Data acquisition and study definitions](docs/DATA_PROCESSING.md) |
| A figure, panel or analysis script | [Figure index](manifests/figure_index.json) · [Panel index](manifests/panel_crosswalk.csv) · [Methods index](manifests/manuscript_crosswalk.csv) |
| A supplementary table value | [Unrounded source data index](manifests/table_source_index.json) · [Displayed cells index](manifests/table_display_index.json) |
| Completed checks and remaining limits | [Verification records](verification/README.md) · [Reproducibility limits](docs/REPRODUCTION.md#what-can-be-recovered) |

**Institutional collaboration.** The [M7 and M8 guide](docs/REPRODUCTION.md#institutional-collaboration-in-m7-and-m8) identifies the current implementations for Extended Data Fig. 8 and Fig. 6. The historical notebooks mark the earlier country-network figures, five-joint-publication edge filter and country shortest-path centrality calculations as retired.

## Version and citation

The figure inputs correspond to the manuscript version of 19 November 2026. The verification records distinguish the original figure checks from later desktop tests.

[Software citation](CITATION.cff) · [Code and data availability](docs/AVAILABILITY.md) · [MIT license](LICENSE) · [Third-party terms](THIRD_PARTY.md)
