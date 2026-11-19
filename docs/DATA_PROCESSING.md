# From source acquisition to the analytical study

## Source and unit of observation

The April 2026 OpenAlex bibliographic acquisition was completed during the week of April 3, as recorded by the study team. The study covers publications dated 2015–2025 in the 22 primary subfields listed in [the scope registry](../pipeline/config/subfields.csv). Twenty-one subfields contributed at least one confirmed AF study in the 2020–2025 main period. The baseline period used to define prior institutional output is 2015–2019. The separate incoming citation collection dates to October 30–31, 2026 and applies a citing-publication cutoff of December 31, 2025.

A work is an OpenAlex bibliographic record. A study can contain multiple approved work versions. An institution–study relation, an author–institution affiliation and a fractional country credit measure different things; their counts cannot be added to the work count.

## Acquisition and evidence review

1. **Bibliographic retrieval.** The historical collector selected OpenAlex works by primary subfield and inclusive publication-date filters, using cursor pagination. Its field set includes work/DOI IDs, publication date, type, title, abstract inverted index, authorships, cited-by count, outgoing references, concepts, primary location and topic information. The processed identifiers and study attributes used for review are in the deposit.
2. **Candidate retrieval.** Keywords and citations to four seed resources identified 29,127 distinct candidate works. The seeds covered AF2, AF-Multimer, the AF Protein Structure Database and AF3. Retrieval flagged records for review; it did not establish adoption. The extended screen yielded 826 additional leads, of which 765 met the work-type scope.
3. **Evidence packets.** The retrieval pipeline located usable evidence, extracted text around relevant mentions and recorded source/tier provenance. Packets were assembled from available full text or abstracts. Unavailable or inconclusive evidence could remain unresolved. Access to a paper or its text at a later date may differ.
4. **Coding and adjudication.** Models A and B used the specified packet, prompt and schema. Core-field disagreements went to Model C under the production protocol. Unresolved core discrepancies and mandatory evidence-review cases went through adjudication. Secondary action coding had its own review policy. Schema checks, literal evidence checks, archive integrity and scientific acceptance are separate stages. A positive adoption requires affirmative use and eligibility in the study’s own work. Citations, discussion or future plans alone are insufficient. The frozen decision includes its route and evidence tier. [Production protocol](../pipeline/config/af_production_protocol_v1.json) · [Prompt](../pipeline/config/af_review_prompt_v4.txt) · [Schema](../pipeline/config/af_review_output_schema_v2.json)
5. **Calibration.** A purposive pilot of 150 candidate works has 122 determinate references; 24 evidence-unresolved and 4 uncertain consensus cases were excluded from the performance denominator. The authors report that human judgements preceded viewing model answers. Of 68 pilot cases routed to C, 53 have determinate references. Reported recall describes classification among these candidates; retrieval sensitivity over OpenAlex is unidentified. Pilot and production records overlap.
6. **Supplementary retrieval.** Of 765 eligible supplemental candidates, 179 had earlier decisive reviews. Of the remaining 586, 556 received A/B packets (154 full-text, 402 abstract), 28 had insufficient evidence and two exceeded the packet limit. C reviewed 516 exception cases. The final supplemental routes comprise 74 use, 159 non-use, one excluded platform and 531 uncertain work records. Seventy-three net study additions increased the main AF cohort from 16,341 to 16,414. The additional candidate records and their years are distributed in the corpus bundle. The supplemental A interface was routed by the provider from DeepSeek V4-Flash to V4.1-Flash.
7. **Version reconciliation.** Document-type eligibility retained articles, reviews and preprints. Only approved links collapse work records into studies. The 4,686,896 eligible records became 4,686,894 study units after the original links and 4,686,879 after revision. The deposited crosswalk is authoritative for joining versions.
8. **Secondary actions.** The separately adjudicated 3,755-work action layer yields 33,714 work–action decisions. Nine works had no parsed response; uncertainty and quarantined attribution remain traceable. The corpus master reflects the earlier decision layer. Apply the separate update and study crosswalk when reproducing downstream analyses. A missing, unresolved or unevaluable action must not be recoded as absent.

## Denominators used in the manuscript

| Stage or analysis | Count | Interpretation |
|---|---:|---|
| Bibliographic master | 6,046,663 | OpenAlex work records, 2015–2025 |
| Eligible works | 4,686,896 | Articles, reviews and preprints in scope |
| Reconciled studies | 4,686,879 | All eligible years after approved links |
| Main-period eligible studies | 2,714,594 | 2020–2025 |
| Confirmed main-period AF studies | 16,414 | Annual counts of 11, 393, 2,389, 3,904, 4,144 and 5,573 |
| Fixed institutional cohort | 48,010 | Baseline-eligible institutions in 68 countries/regions satisfying the final coverage rules |
| International authorship common support | 5,087 AF and 332,760 reference | Final Fig. 3 and Fig. 4 weighting across 173 cells |
| Citation observations with a known 12-month count | 1,876,834 | Complete-window and quality rules applied to the main-period frame |

National analyses use fractional country credit with a fixed 227-unit registry. Institutional lower/middle/higher groups follow 2015–2019 output within country, with ties handled by the frozen protocol. They are distinct from national output groups and from World Bank income groups. Other figures restrict follow-up, measurable role credit, matching support or outcome availability. Use the figure/table source and its denominator before comparing counts.

## Derived outcomes

Incoming citation edges identify citing studies and dates. Counts use publication-based windows with the end date excluded, study-level deduplication and quarantine rules. The 12-month analysis covers mature publications through 2024 and the 24-month sensitivity through 2023. A missing or quarantined count remains missing. Contemporary cumulative cited-by counts and outgoing references cannot reconstruct an exhaustive incoming fixed-window history.

Historical journal position is a percentile based on the annual SJR distribution among eligible journals in a category. Average tied ascending ranks, convert to a 0–100 scale, and average usable category percentiles for a journal-year. Historical matching uses valid ISSNs and retains unavailable or ambiguous matches. The result describes the publishing venue. For Fig. 5, compare AF studies to eligible screen-negative papers from the same institution, year, subfield and document type, and then average institution-level contrasts. Fig. 6 examines associations with observed co-publication network measures.

## Reacquiring inputs

List the registered subfields locally, then request each chosen subfield into a private working directory. Supply OPENALEX_API_KEY through your own environment. A live request can incur provider charges. The original JSONL and article text are excluded from the release.

```sh
python pipeline/download_openalex.py --list
python pipeline/download_openalex.py --subfield 1315 --destination ../private-openalex
```

The collector resumes through per-subfield checkpoints. Its output belongs in the private acquisition workspace. The original notebook and the relational preparation stages are under pipeline/code. Scripts 03–10 document full-text retrieval, context preparation, packet construction and checks. Scripts 11–32 document pilot calibration. Scripts 33–47 document production, adjudication and final validation. Historical runs also required provider access, licensed content as available, human review, configuration and private runtime artifacts. The original evidence text and human workbooks cannot be replayed from the public deposit alone.

The fixed analytic snapshot is provided in Parquet. The April and October retrievals are separately dated; repeating either request against a live database can yield revised records. For provider-supplied journal data, obtain the eleven full lists for 2015–2025 and use the [journal rebuild command](REPRODUCTION.md). Input SHA-256 values in [source fingerprints](../manifests/source_fingerprints.csv) distinguish snapshot versions. The Zenodo file and Parquet dictionaries identify the specific archive, file, row counts, columns and Arrow types. [Source attribution](../THIRD_PARTY.md)
