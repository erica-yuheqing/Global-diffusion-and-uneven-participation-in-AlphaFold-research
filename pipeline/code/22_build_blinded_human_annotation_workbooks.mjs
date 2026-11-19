#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const WORKBOOK_SCHEMA = "af-human-annotation-workbook-v1";
const RUNTIME_BUNDLE = "26.905.11957";
const FONT = "Arial";
const HEADER_FILL = "#233B53";
const HEADER_TEXT = "#FFFFFF";
const INPUT_FILL = "#FFF4CC";
const SOURCE_FILL = "#F3F6F8";
const BORDER = "#D5DCE3";
const TEXT = "#1F2933";
const MUTED = "#5B6875";
const ACCENT = "#2D6A8E";

function parseArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) continue;
    const next = argv[index + 1];
    if (next && !next.startsWith("--")) {
      result[token.slice(2)] = next;
      index += 1;
    } else {
      result[token.slice(2)] = true;
    }
  }
  return result;
}

function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function sha256Buffer(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

async function sha256File(filePath) {
  return sha256Buffer(await fs.readFile(filePath));
}

async function readJson(filePath) {
  return JSON.parse(await fs.readFile(filePath, "utf8"));
}

async function readJsonl(filePath) {
  return (await fs.readFile(filePath, "utf8"))
    .split(/\r?\n/)
    .filter((line) => line.trim())
    .map((line) => JSON.parse(line));
}

function asText(value) {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return value.map(asText).filter(Boolean).join(" | ");
  if (typeof value === "object") return canonicalJson(value);
  return String(value);
}

function materialAvailability(record) {
  const material = record.input_material || {};
  const quality = record.input_quality || {};
  const abstractUsable = quality.abstract_status === "usable" && Boolean((material.abstract || "").trim());
  const hasBlocks = (material.evidence_blocks || []).length > 0;
  if (abstractUsable && hasBlocks) return "abstract + supplied body blocks";
  if (hasBlocks) return "supplied body blocks only";
  if (abstractUsable) return "abstract only";
  return "no usable supplied text";
}

function setFont(range, size = 10) {
  range.format.font = { name: FONT, size, color: TEXT };
}

function styleHeader(range) {
  range.format.fill = HEADER_FILL;
  range.format.font = { name: FONT, size: 10, bold: true, color: HEADER_TEXT };
  range.format.horizontalAlignment = "center";
  range.format.verticalAlignment = "center";
  range.format.wrapText = true;
  range.format.borders = {
    bottom: { style: "medium", color: HEADER_FILL },
    insideVertical: { style: "thin", color: "#FFFFFF" },
  };
}

function styleTitle(sheet, title, subtitle, endColumn = "H") {
  sheet.showGridLines = false;
  sheet.getRange("A1").values = [[title]];
  sheet.getRange("A1").format.font = { name: FONT, size: 16, bold: true, color: TEXT };
  sheet.getRange("A2").values = [[subtitle]];
  sheet.getRange("A2").format.font = { name: FONT, size: 10, italic: true, color: MUTED };
  sheet.getRange(`A3:${endColumn}3`).format.borders = {
    bottom: { style: "thin", color: ACCENT },
  };
  sheet.getRange("A1:A3").format.rowHeightPx = 24;
}

function styleBody(range) {
  setFont(range, 10);
  range.format.verticalAlignment = "top";
  range.format.wrapText = true;
}

function addListValidation(sheet, address, values) {
  sheet.getRange(address).dataValidation = {
    allowBlank: true,
    list: { inCellDropDown: true, source: values },
  };
}

function buildInstructions(workbook, annotatorId, recordCount, protocolVersion) {
  const sheet = workbook.worksheets.getItem("Instructions");
  styleTitle(
    sheet,
    "AlphaFold adoption pilot — independent annotation",
    `Assignment ${annotatorId}; ${recordCount} records; protocol ${protocolVersion}`,
    "H",
  );

  sheet.getRange("A5:B10").values = [
    ["Progress", "Value"],
    ["Assigned records", null],
    ["Complete", null],
    ["Pending", null],
    ["Uncertain primary label", null],
    ["Blank primary label", null],
  ];
  styleHeader(sheet.getRange("A5:B5"));
  const finalRow = recordCount + 1;
  sheet.getRange("B6").formulas = [[`=COUNTA(Annotations!$C$2:$C$${finalRow})`]];
  sheet.getRange("B7").formulas = [[`=COUNTIF(Annotations!$AL$2:$AL$${finalRow},\"complete\")`]];
  sheet.getRange("B8").formulas = [[`=COUNTIF(Annotations!$AL$2:$AL$${finalRow},\"pending\")`]];
  sheet.getRange("B9").formulas = [[`=COUNTIF(Annotations!$I$2:$I$${finalRow},\"uncertain\")`]];
  sheet.getRange("B10").formulas = [[`=COUNTBLANK(Annotations!$I$2:$I$${finalRow})`]];
  styleBody(sheet.getRange("A6:B10"));
  sheet.getRange("B6:B10").format.numberFormat = "#,##0";

  const guidance = [
    ["Independent and blinded review"],
    ["Do not open the machine-consensus files, old retrieval labels, or the other annotator's workbook until both independent annotations are locked."],
    ["Use only the supplied Paper Text and Evidence Blocks. Do not use outside knowledge, author country, institution, journal prestige, or the record's presence in this dataset."],
    ["Workflow"],
    ["1. Select a row in Annotations. Use review_id or reviewer_record_id to filter Paper Text and Evidence Blocks."],
    ["2. Read the usable abstract and supplied body blocks. A citation or title alone cannot establish actual use."],
    ["3. Complete the structured labels. Use uncertain/RU when the supplied material cannot resolve the level; absence of evidence is not evidence of non-use."],
    ["4. Enter 1–3 exact excerpts of no more than 25 whitespace-delimited words. Copy source_kind, block_index, and section exactly."],
    ["5. Separate multiple observed_actions and uncertainty_reasons with |. Use action_evidence_map such as ran_alphafold:1 | integrated_empirical_workflow:1,2."],
    ["6. Set status=complete only after checking consistency and entering annotator_id and annotation_date."],
    ["Key boundary rules"],
    ["R3 is actual downstream use in an empirical workflow. R4 requires substantive methodological benchmarking, modification, extension, or downstream method/tool development."],
    ["Running ColabFold counts as AlphaFold-technology use and can support use=yes and adoption=yes."],
    ["AF use=yes means this study actually used AF technology or its predictions. Adoption=yes means downstream application; original AF platform development is use=yes but adoption=no."],
    ["A target-specific comparison with an experimental structure can be R3 with benchmarked_or_evaluated; it is not automatically R4."],
    ["E2 is explicit abstract/title evidence without body confirmation. E3 requires attributable evidence in a supplied full-text body block."],
    ["Completion check"],
    ["Required: primary/R/E/relation/use/adoption/future flag/actions/exclusion, 1–3 evidence excerpts, reasoning summary, annotator ID, date, and status."],
  ];
  sheet.getRange("D5:D22").values = guidance;
  for (const cell of ["D5", "D8", "D15", "D21"]) {
    sheet.getRange(cell).format.fill = "#DCEAF3";
    sheet.getRange(cell).format.font = { name: FONT, size: 11, bold: true, color: TEXT };
  }
  styleBody(sheet.getRange("D6:D22"));
  sheet.getRange("D5:D22").format.columnWidthPx = 880;
  sheet.getRange("D5:D22").format.rowHeightPx = 40;
  sheet.getRange("D6:D7").format.rowHeightPx = 56;
  sheet.getRange("A5:A10").format.columnWidthPx = 210;
  sheet.getRange("B5:B10").format.columnWidthPx = 110;
  sheet.freezePanes.freezeRows(3);
  sheet.tabColor = "#2D6A8E";
  return sheet;
}

const ANNOTATION_HEADERS = [
  "assignment_order",
  "reviewer_record_id",
  "review_id",
  "work_id",
  "title",
  "publication_year",
  "doi",
  "material_available",
  "primary_label",
  "relevance_level",
  "evidence_level",
  "af_related_label",
  "af_use_label",
  "adoption_eligible",
  "future_or_hypothetical_only",
  "observed_actions",
  "action_evidence_map",
  "exclusion_reason",
  "evidence_1_source_kind",
  "evidence_1_block_index",
  "evidence_1_section",
  "evidence_1_quote",
  "evidence_1_supports",
  "evidence_2_source_kind",
  "evidence_2_block_index",
  "evidence_2_section",
  "evidence_2_quote",
  "evidence_2_supports",
  "evidence_3_source_kind",
  "evidence_3_block_index",
  "evidence_3_section",
  "evidence_3_quote",
  "evidence_3_supports",
  "uncertainty_reasons",
  "reasoning_summary",
  "annotator_id",
  "annotation_date",
  "status",
];

function buildAnnotations(workbook, assignment, packetByReviewId) {
  const sheet = workbook.worksheets.getItem("Annotations");
  const rows = assignment.records.map((entry) => {
    const record = packetByReviewId.get(entry.review_id);
    const material = record.input_material || {};
    return [
      entry.assignment_order,
      entry.reviewer_record_id,
      entry.review_id,
      entry.work_id,
      material.title || "",
      material.publication_year ?? null,
      material.doi || "",
      materialAvailability(record),
      "",
      "",
      "",
      "",
      "",
      "",
      "",
      "",
      "",
      "",
      "",
      null,
      "",
      "",
      "",
      "",
      null,
      "",
      "",
      "",
      "",
      null,
      "",
      "",
      "",
      "",
      "",
      "",
      null,
      "pending",
    ];
  });
  sheet.getRange("A1:AL1").values = [ANNOTATION_HEADERS];
  sheet.getRange("A2").write(rows);
  sheet.tables.add(`A1:AL${rows.length + 1}`, true, `Annotations${assignment.annotator_id}`);
  styleHeader(sheet.getRange("A1:AL1"));
  sheet.getRange("A1:AL1").format.rowHeightPx = 54;
  styleBody(sheet.getRange(`A2:AL${rows.length + 1}`));
  sheet.getRange(`A2:H${rows.length + 1}`).format.fill = SOURCE_FILL;
  sheet.getRange(`I2:AL${rows.length + 1}`).format.fill = INPUT_FILL;
  sheet.getRange(`A2:AL${rows.length + 1}`).format.rowHeightPx = 48;
  sheet.getRange(`A2:D${rows.length + 1}`).format.horizontalAlignment = "center";
  sheet.getRange(`F2:F${rows.length + 1}`).format.horizontalAlignment = "center";
  sheet.getRange(`T2:T${rows.length + 1}`).format.horizontalAlignment = "center";
  sheet.getRange(`Y2:Y${rows.length + 1}`).format.horizontalAlignment = "center";
  sheet.getRange(`AD2:AD${rows.length + 1}`).format.horizontalAlignment = "center";
  sheet.getRange(`AK2:AK${rows.length + 1}`).format.numberFormat = "yyyy-mm-dd";

  const widths = {
    A: 72, B: 96, C: 78, D: 118, E: 290, F: 82, G: 200, H: 170,
    I: 145, J: 92, K: 92, L: 110, M: 90, N: 110, O: 130,
    P: 250, Q: 260, R: 170, S: 125, T: 95, U: 190, V: 340, W: 160,
    X: 125, Y: 95, Z: 190, AA: 340, AB: 160, AC: 125, AD: 95,
    AE: 190, AF: 340, AG: 160, AH: 230, AI: 360, AJ: 105, AK: 110, AL: 95,
  };
  for (const [column, width] of Object.entries(widths)) {
    sheet.getRange(`${column}1:${column}${rows.length + 1}`).format.columnWidthPx = width;
  }

  addListValidation(sheet, `I2:I${rows.length + 1}`, [
    "FP", "background_only", "review_discussion", "database_consumption",
    "model_application", "method_development", "original_platform", "uncertain",
  ]);
  addListValidation(sheet, `J2:J${rows.length + 1}`, ["R0", "R1", "R2", "R3", "R4", "RU"]);
  addListValidation(sheet, `K2:K${rows.length + 1}`, ["E0", "E1", "E2", "E3"]);
  addListValidation(sheet, `L2:L${rows.length + 1}`, ["false", "background", "related", "uncertain"]);
  addListValidation(sheet, `M2:N${rows.length + 1}`, ["no", "yes", "uncertain"]);
  addListValidation(sheet, `O2:O${rows.length + 1}`, ["no", "yes"]);
  addListValidation(sheet, `R2:R${rows.length + 1}`, [
    "none", "unrelated_or_abbreviation", "background_only", "review_no_use",
    "original_platform", "insufficient_evidence", "future_hypothetical_only", "other",
  ]);
  for (const column of ["S", "X", "AC"]) {
    addListValidation(sheet, `${column}2:${column}${rows.length + 1}`, [
      "title", "abstract", "fulltext_block", "matched_reference",
    ]);
  }
  addListValidation(sheet, `AL2:AL${rows.length + 1}`, ["pending", "complete"]);

  sheet.getRange(`AL2:AL${rows.length + 1}`).conditionalFormats.add("containsText", {
    text: "complete",
    format: { fill: "#D9EAD3", font: { color: "#1B5E20", bold: true } },
  });
  sheet.getRange(`AL2:AL${rows.length + 1}`).conditionalFormats.add("containsText", {
    text: "pending",
    format: { fill: "#FFF2CC", font: { color: "#7F6000" } },
  });
  sheet.getRange(`I2:I${rows.length + 1}`).conditionalFormats.add("containsText", {
    text: "uncertain",
    format: { fill: "#FCE8E6", font: { color: "#9C2B1E", bold: true } },
  });

  sheet.freezePanes.freezeRows(1);
  sheet.freezePanes.freezeColumns(4);
  sheet.tabColor = "#C18B00";
  return sheet;
}

function buildPaperText(workbook, assignment, packetByReviewId) {
  const sheet = workbook.worksheets.add("Paper Text");
  const headers = [
    "assignment_order", "reviewer_record_id", "review_id", "work_id", "title",
    "publication_year", "doi", "work_type", "domain_labels", "material_available",
    "abstract_status", "fulltext_body_available", "quality_flags", "abstract",
    "fulltext_source", "packet_sha256",
  ];
  const rows = assignment.records.map((entry) => {
    const record = packetByReviewId.get(entry.review_id);
    const material = record.input_material || {};
    const quality = record.input_quality || {};
    const usableAbstract = quality.abstract_status === "usable" ? material.abstract || "" : "";
    return [
      entry.assignment_order,
      entry.reviewer_record_id,
      entry.review_id,
      entry.work_id,
      material.title || "",
      material.publication_year ?? null,
      material.doi || "",
      material.work_type || "",
      asText(material.domain_labels),
      materialAvailability(record),
      quality.abstract_status || "",
      Boolean(quality.fulltext_body_available),
      asText(quality.flags || []),
      usableAbstract,
      material.fulltext_source || "",
      record.packet_sha256,
    ];
  });
  sheet.getRange("A1:P1").values = [headers];
  sheet.getRange("A2").write(rows);
  sheet.tables.add(`A1:P${rows.length + 1}`, true, `PaperText${assignment.annotator_id}`);
  styleHeader(sheet.getRange("A1:P1"));
  sheet.getRange("A1:P1").format.rowHeightPx = 48;
  styleBody(sheet.getRange(`A2:P${rows.length + 1}`));
  sheet.getRange(`A2:P${rows.length + 1}`).format.rowHeightPx = 110;
  const widths = [72, 96, 78, 118, 300, 82, 210, 110, 150, 180, 120, 120, 180, 620, 130, 360];
  for (let index = 0; index < widths.length; index += 1) {
    sheet.getRangeByIndexes(0, index, rows.length + 1, 1).format.columnWidthPx = widths[index];
  }
  sheet.freezePanes.freezeRows(1);
  sheet.freezePanes.freezeColumns(4);
  sheet.tabColor = "#6B879B";
  return sheet;
}

function buildEvidenceBlocks(workbook, assignment, packetByReviewId) {
  const sheet = workbook.worksheets.add("Evidence Blocks");
  const headers = [
    "assignment_order", "reviewer_record_id", "review_id", "work_id", "source_kind",
    "block_index", "section", "role", "trigger_types", "matched_values", "text", "source_ref",
  ];
  const rows = [];
  for (const entry of assignment.records) {
    const record = packetByReviewId.get(entry.review_id);
    const material = record.input_material || {};
    rows.push([
      entry.assignment_order, entry.reviewer_record_id, entry.review_id, entry.work_id,
      "title", null, "", "source", "", "", material.title || "", "title",
    ]);
    if (record.input_quality?.abstract_status === "usable" && (material.abstract || "").trim()) {
      rows.push([
        entry.assignment_order, entry.reviewer_record_id, entry.review_id, entry.work_id,
        "abstract", null, "Abstract", "source", "", "", material.abstract, "abstract",
      ]);
    }
    for (const reference of material.matched_seed_references || []) {
      rows.push([
        entry.assignment_order, entry.reviewer_record_id, entry.review_id, entry.work_id,
        "matched_reference", null, "References", "matched_reference",
        asText(reference.seed_ids || []), asText(reference.citation_labels || []),
        reference.reference_text || "", `matched_reference:${reference.reference_id || ""}`,
      ]);
    }
    for (const block of material.evidence_blocks || []) {
      rows.push([
        entry.assignment_order, entry.reviewer_record_id, entry.review_id, entry.work_id,
        "fulltext_block", block.index ?? null, block.section || "", block.role || "",
        asText(block.trigger_types || []), asText(block.matched_values || {}),
        block.text || "", `fulltext_block:${block.index ?? ""}`,
      ]);
    }
  }
  sheet.getRange("A1:L1").values = [headers];
  sheet.getRange("A2").write(rows);
  sheet.tables.add(`A1:L${rows.length + 1}`, true, `EvidenceBlocks${assignment.annotator_id}`);
  styleHeader(sheet.getRange("A1:L1"));
  sheet.getRange("A1:L1").format.rowHeightPx = 48;
  styleBody(sheet.getRange(`A2:L${rows.length + 1}`));
  sheet.getRange(`A2:L${rows.length + 1}`).format.rowHeightPx = 88;
  const widths = [72, 96, 78, 118, 125, 90, 200, 105, 190, 230, 650, 150];
  for (let index = 0; index < widths.length; index += 1) {
    sheet.getRangeByIndexes(0, index, rows.length + 1, 1).format.columnWidthPx = widths[index];
  }
  sheet.freezePanes.freezeRows(1);
  sheet.freezePanes.freezeColumns(4);
  sheet.tabColor = "#6B879B";
  return { sheet, rowCount: rows.length };
}

function buildCodebook(workbook, protocolVersion) {
  const sheet = workbook.worksheets.add("Codebook");
  styleTitle(sheet, "Annotation codebook", `Protocol ${protocolVersion}; controlled values remain in English for machine import`, "D");
  const rows = [
    ["Category", "Value", "Definition", "Consistency note"],
    ["Primary label", "FP", "Confirmed false positive or unrelated AlphaFold abbreviation.", "R0; related=false; use=no; adoption=no."],
    ["Primary label", "background_only", "Landmark citation or incidental background mention without substantive discussion or use.", "R1; related=background; use=no; adoption=no."],
    ["Primary label", "review_discussion", "Substantive discussion, review, commentary, or literature comparison without actual use by this study.", "R2; related=related; use=no; adoption=no."],
    ["Primary label", "database_consumption", "Obtained or analyzed an existing AlphaFold Database or other precomputed AF structure.", "R3; related=related; use=yes; adoption=yes."],
    ["Primary label", "model_application", "Ran AF/ColabFold or integrated/evaluated AF predictions in an empirical workflow.", "R3; related=related; use=yes; adoption=yes."],
    ["Primary label", "method_development", "Systematic methodological benchmarking, modification, extension, or downstream method/tool development.", "R4; related=related; use=yes; adoption=yes."],
    ["Primary label", "original_platform", "Original AlphaFold model, database, or official platform development.", "R4; related=related; use=yes; adoption=no; exclude as original_platform."],
    ["Primary label", "uncertain", "Supplied material cannot resolve the primary level.", "Use RU; preserve narrower related/use/adoption facts only when explicit."],
    ["Relevance", "R0", "Confirmed unrelated or false positive.", "Do not use for missing evidence."],
    ["Relevance", "R1", "Background or citation only.", "No actual use."],
    ["Relevance", "R2", "Substantive discussion without study use.", "No actual use."],
    ["Relevance", "R3", "Actual downstream use in an empirical workflow.", "Includes target-specific evaluation and ColabFold use."],
    ["Relevance", "R4", "Substantive method/platform development or systematic methodological contribution.", "Target-specific comparison alone is not automatically R4."],
    ["Relevance", "RU", "R level cannot be assigned reliably.", "Not equivalent to R0."],
    ["Evidence", "E0", "No usable scientific abstract or body evidence.", "Title-only or contaminated material cannot establish actual use."],
    ["Evidence", "E1", "Weak or indirect evidence: metadata/title signal, hypothetical use, or unlinked citation.", "Cannot establish actual use."],
    ["Evidence", "E2", "Explicit title/abstract evidence supports the decision; procedural/body confirmation is absent.", "Abstract-only actual use should be marked for uncertainty/adjudication."],
    ["Evidence", "E3", "Explicit attributable evidence in a supplied full-text body block.", "Title, abstract, or bibliography alone is not E3."],
    ["Action", "retrieved_precomputed_structure", "Explicitly obtained an existing AFDB/precomputed model.", "Do not infer from the word AlphaFold alone."],
    ["Action", "ran_alphafold", "Explicit procedure states this study ran AlphaFold.", "A predicted model's existence or origin alone does not prove execution."],
    ["Action", "ran_colabfold", "Explicit procedure states this study ran ColabFold.", "Counts as AF-technology use; do not automatically also add ran_alphafold."],
    ["Action", "integrated_empirical_workflow", "Used AF predictions for interpretation, fitting, docking, screening, or empirical analysis.", "Cryo-EM map fitting belongs here."],
    ["Action", "docking_or_screening", "Molecular/ligand/protein-interaction docking or virtual screening using an AF prediction.", "Do not use for rigid fitting into an electron-density map."],
    ["Action", "benchmarked_or_evaluated", "Actually evaluated prediction accuracy, quality, confidence, failures, or limitations.", "May occur in R3 or R4."],
    ["Action", "modified_or_extended", "Explicit AlphaFold method modification or extension.", "Requires direct evidence."],
    ["Action", "developed_downstream_tool", "Developed a downstream tool or method that materially uses AF outputs.", "Requires direct evidence."],
    ["Action", "discussion_only", "Substantive AF discussion without actual use.", "Cannot coexist with an actual-use action."],
    ["Action", "none", "No supported observed action.", "Cannot coexist with another action."],
    ["Uncertainty reason", "abstract_only", "Actual-use decision relies only on title/abstract evidence.", "Use | between multiple reasons."],
    ["Uncertainty reason", "insufficient_evidence", "Supplied evidence cannot support a stable decision.", "Use uncertain/RU where appropriate."],
    ["Uncertainty reason", "boundary_R2_R3", "Discussion versus actual study use remains unresolved.", "Requires adjudication."],
    ["Uncertainty reason", "boundary_R3_R4", "Application versus methodological contribution remains unresolved.", "Requires adjudication."],
    ["Uncertainty reason", "original_vs_downstream", "Original platform development versus downstream adoption remains ambiguous.", "Requires adjudication."],
    ["Uncertainty reason", "conflicting_evidence", "Supplied passages support incompatible interpretations.", "Explain in reasoning_summary."],
    ["Uncertainty reason", "citation_link_uncertain", "Citation linkage to AlphaFold or to the study's procedure is unclear.", "Bibliography cannot prove execution."],
    ["Uncertainty reason", "prediction_origin_unclear", "Prediction was used but it is unclear whether authors ran or retrieved it.", "Retain supported integration/use; omit unproven run action."],
    ["Uncertainty reason", "input_quality", "Source text is missing, contaminated, or otherwise unreliable.", "Describe the issue."],
    ["Uncertainty reason", "other", "A material uncertainty not represented above.", "Explain in reasoning_summary."],
  ];
  sheet.getRange("A5:D5").values = [rows[0]];
  sheet.getRange("A6").write(rows.slice(1));
  styleHeader(sheet.getRange("A5:D5"));
  styleBody(sheet.getRange(`A6:D${rows.length + 4}`));
  sheet.getRange(`A5:D${rows.length + 4}`).format.borders = {
    bottom: { style: "thin", color: BORDER },
  };
  const widths = [145, 205, 590, 390];
  for (let index = 0; index < widths.length; index += 1) {
    sheet.getRangeByIndexes(4, index, rows.length, 1).format.columnWidthPx = widths[index];
  }
  sheet.getRange(`A6:D${rows.length + 4}`).format.rowHeightPx = 56;
  sheet.freezePanes.freezeRows(5);
  sheet.tabColor = "#2D6A8E";
  return sheet;
}

function buildMetadata(workbook, assignment, manifest, outputFileName, evidenceRowCount) {
  const sheet = workbook.worksheets.add("Metadata");
  styleTitle(sheet, "Reproducibility metadata", "Immutable identifiers and hashes for this blinded assignment", "B");
  const assignmentMeta = manifest.assignment_files[assignment.annotator_id];
  const rows = [
    ["field", "value"],
    ["workbook_schema_version", WORKBOOK_SCHEMA],
    ["version_tag", manifest.version_tag || "v4_3"],
    ["protocol_version", manifest.protocol_version || "af-review-v2"],
    ["assignment_id", assignment.annotator_id],
    ["record_count", assignment.record_count],
    ["evidence_block_rows_in_workbook", evidenceRowCount],
    ["assignment_seed", assignment.seed],
    ["ordered_review_id_sha256", assignment.ordered_review_id_sha256],
    ["assignment_file", assignmentMeta.file],
    ["assignment_file_sha256", assignmentMeta.sha256],
    ["packet_file", manifest.packet_file],
    ["packet_file_sha256", manifest.packet_file_sha256],
    ["source_file", manifest.source_file],
    ["source_file_sha256", manifest.source_file_sha256],
    ["context_policy_versions", asText(manifest.context_policy_versions || [])],
    ["codebook_source", manifest.codebook_source.file],
    ["codebook_source_sha256", manifest.codebook_source.sha256],
    ["output_schema_source", manifest.output_schema_source.file],
    ["output_schema_source_sha256", manifest.output_schema_source.sha256],
    ["manifest_created_at_utc", `ISO 8601: ${manifest.created_at_utc}`],
    ["workbook_file", outputFileName],
    ["runtime_bundle", RUNTIME_BUNDLE],
    ["node_version", process.version],
    ["machine_outputs_included", false],
    ["old_retrieval_labels_included", false],
    ["sampling_fields_included", false],
    ["independent_assignment_order", true],
    ["prohibited_fields", manifest.blinding.prohibited_keys.join(" | ")],
    ["blinding_note", "Machine A/B/C labels and old retrieval/sampling fields are excluded. Paper identity and supplied scientific evidence remain visible for auditability."],
  ];
  sheet.getRange("A5:B5").values = [rows[0]];
  sheet.getRange("A6").write(rows.slice(1));
  styleHeader(sheet.getRange("A5:B5"));
  styleBody(sheet.getRange(`A6:B${rows.length + 4}`));
  sheet.getRange(`A5:A${rows.length + 4}`).format.columnWidthPx = 260;
  sheet.getRange(`B5:B${rows.length + 4}`).format.columnWidthPx = 760;
  sheet.getRange(`A6:B${rows.length + 4}`).format.rowHeightPx = 40;
  sheet.freezePanes.freezeRows(5);
  sheet.tabColor = "#777777";
  return sheet;
}

function buildWorkbook(assignment, packets, manifest, outputFileName) {
  const workbook = Workbook.create();
  // Create formula-referenced sheets before writing formulas so recalculation
  // can resolve stable worksheet identifiers in the authoring runtime.
  workbook.worksheets.add("Instructions");
  workbook.worksheets.add("Annotations");
  const packetByReviewId = new Map(packets.map((record) => [record.review_id, record]));
  for (const entry of assignment.records) {
    const packet = packetByReviewId.get(entry.review_id);
    if (!packet) throw new Error(`Assignment ${assignment.annotator_id}: missing ${entry.review_id}`);
    if (packet.work_id !== entry.work_id || packet.packet_sha256 !== entry.packet_sha256) {
      throw new Error(`Assignment ${assignment.annotator_id}: identity/hash mismatch for ${entry.review_id}`);
    }
  }
  const protocolVersion = manifest.protocol_version || "af-review-v2";
  buildInstructions(workbook, assignment.annotator_id, assignment.record_count, protocolVersion);
  buildAnnotations(workbook, assignment, packetByReviewId);
  buildPaperText(workbook, assignment, packetByReviewId);
  const evidenceResult = buildEvidenceBlocks(workbook, assignment, packetByReviewId);
  const evidenceRowCount = evidenceResult.rowCount;
  buildCodebook(workbook, protocolVersion);
  buildMetadata(workbook, assignment, manifest, outputFileName, evidenceRowCount);
  return workbook;
}

async function verifyAndRenderSavedWorkbook(filePath, previewDir, annotatorId) {
  const imported = await SpreadsheetFile.importXlsx(await FileBlob.load(filePath));
  const overview = await imported.inspect({
    kind: "workbook,sheet,table",
    maxChars: 8000,
    tableMaxRows: 4,
    tableMaxCols: 8,
    tableMaxCellChars: 80,
  });
  const errors = await imported.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
    options: { useRegex: true, maxResults: 300 },
    summary: "final formula error scan",
  });
  await fs.mkdir(previewDir, { recursive: true });
  await fs.writeFile(path.join(previewDir, `annotator_${annotatorId}_inspect.ndjson`), `${overview.ndjson}\n${errors.ndjson}\n`);

  const previews = [
    ["Instructions", "A1:H29", "instructions"],
    ["Annotations", "A1:P10", "annotations_labels"],
    ["Annotations", "Q1:AL8", "annotations_evidence"],
    ["Paper Text", "A1:P6", "paper_text"],
    ["Evidence Blocks", "A1:L10", "evidence_blocks"],
    ["Codebook", "A1:D43", "codebook"],
    ["Metadata", "A1:B35", "metadata"],
  ];
  for (const [sheetName, range, suffix] of previews) {
    const blob = await imported.render({ sheetName, range, scale: 1, format: "png" });
    await fs.writeFile(
      path.join(previewDir, `annotator_${annotatorId}_${suffix}.png`),
      new Uint8Array(await blob.arrayBuffer()),
    );
  }
  return { overview: overview.ndjson, errors: errors.ndjson };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const packetFile = path.resolve(args.packets || "fulltext/pilot/human_annotation_v4_3/pilot_150_human_packets_blinded_v4_3.jsonl");
  const assignmentAFile = path.resolve(args["assignment-a"] || "fulltext/pilot/human_annotation_v4_3/pilot_150_annotator_a_assignment_v4_3.json");
  const assignmentBFile = path.resolve(args["assignment-b"] || "fulltext/pilot/human_annotation_v4_3/pilot_150_annotator_b_assignment_v4_3.json");
  const manifestFile = path.resolve(args.manifest || "fulltext/pilot/human_annotation_v4_3/pilot_150_human_annotation_manifest_v4_3.json");
  const outputDir = path.resolve(args["output-dir"] || "outputs/01a0091f-5dc1-7010-b3cd-76ccabfd945c/human_annotation_v4_3");
  const previewDir = path.join(outputDir, "previews");
  await fs.mkdir(outputDir, { recursive: true });

  const [packets, assignmentA, assignmentB, manifest] = await Promise.all([
    readJsonl(packetFile), readJson(assignmentAFile), readJson(assignmentBFile), readJson(manifestFile),
  ]);
  const expectedRecords = Number(manifest.record_count || 150);
  if (packets.length !== expectedRecords || assignmentA.record_count !== expectedRecords || assignmentB.record_count !== expectedRecords) {
    throw new Error(`Expected exactly ${expectedRecords} blinded packets in both assignments`);
  }
  if ((await sha256File(packetFile)) !== manifest.packet_file_sha256) {
    throw new Error("Packet-file hash does not match the frozen human-annotation manifest");
  }
  if (assignmentA.ordered_review_id_sha256 === assignmentB.ordered_review_id_sha256) {
    throw new Error("Annotator assignments unexpectedly have the same record order");
  }

  const versionTag = String(args["version-tag"] || manifest.version_tag || "v4_3");
  if (!/^[A-Za-z0-9_-]+$/.test(versionTag)) throw new Error("Invalid --version-tag");
  const outputAName = `pilot_150_annotator_A_blinded_${versionTag}.xlsx`;
  const outputBName = `pilot_150_annotator_B_blinded_${versionTag}.xlsx`;
  const outputs = [];
  for (const [assignment, fileName] of [[assignmentA, outputAName], [assignmentB, outputBName]]) {
    const workbook = buildWorkbook(assignment, packets, manifest, fileName);
    const outputPath = path.join(outputDir, fileName);
    try {
      await fs.access(outputPath);
      if (!args.force) throw new Error(`Output exists: ${outputPath}; pass --force to replace it`);
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
    }
    workbook.recalculate();
    const blob = await SpreadsheetFile.exportXlsx(workbook);
    await blob.save(outputPath);
    const verification = await verifyAndRenderSavedWorkbook(outputPath, previewDir, assignment.annotator_id);
    const hash = await sha256File(outputPath);
    await fs.writeFile(`${outputPath}.sha256`, `${hash}  ${fileName}\n`, "utf8");
    outputs.push({
      assignment_id: assignment.annotator_id,
      file: fileName,
      sha256: hash,
      record_count: assignment.record_count,
      ordered_review_id_sha256: assignment.ordered_review_id_sha256,
      formula_error_scan: verification.errors,
    });
    console.log(`Workbook ${assignment.annotator_id}: ${outputPath}`);
  }

  const workbookManifest = {
    schema_version: "af-human-annotation-workbook-manifest-v1",
    created_at_utc: new Date().toISOString(),
    runtime_bundle: RUNTIME_BUNDLE,
    node_version: process.version,
    source_manifest_file: path.basename(manifestFile),
    source_manifest_sha256: await sha256File(manifestFile),
    version_tag: versionTag,
    protocol_version: manifest.protocol_version || "af-review-v2",
    builder_file: path.basename(process.argv[1]),
    builder_sha256: await sha256File(path.resolve(process.argv[1])),
    output_directory: path.basename(outputDir),
    workbooks: outputs,
  };
  const workbookManifestPath = path.resolve(
    args["workbook-manifest"] || path.join(path.dirname(manifestFile), `pilot_150_human_workbook_manifest_${versionTag}.json`),
  );
  const manifestText = `${JSON.stringify(workbookManifest, null, 2)}\n`;
  await fs.writeFile(workbookManifestPath, manifestText, "utf8");
  await fs.writeFile(
    `${workbookManifestPath}.sha256`,
    `${sha256Buffer(Buffer.from(manifestText))}  ${path.basename(workbookManifestPath)}\n`,
    "utf8",
  );
  console.log(`Workbook manifest: ${workbookManifestPath}`);
}

await main();
