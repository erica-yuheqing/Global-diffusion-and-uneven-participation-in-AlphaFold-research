#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const PROJECT_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SCHEMA_VERSION = "af-human-adjudication-workbook-v1";
const FONT = "Arial";
const HEADER_FILL = "#233B53";
const HEADER_TEXT = "#FFFFFF";
const SOURCE_FILL = "#F3F6F8";
const INPUT_FILL = "#FFF4CC";
const BORDER = "#D5DCE3";
const TEXT = "#1F2933";
const MUTED = "#5B6875";
const ACCENT = "#2D6A8E";
const ALERT_FILL = "#FCE8E6";
const ALERT_TEXT = "#9C2B1E";

const DEFAULTS = {
  disagreements: "fulltext/pilot/human_annotation_v6/results_repaired/pilot_150_human_disagreements_repaired_v6.csv",
  annotatorA: "fulltext/pilot/human_annotation_v6/repaired/pilot_150_annotator_A_repaired_v6.xlsx",
  annotatorB: "fulltext/pilot/human_annotation_v6/repaired/pilot_150_annotator_B_repaired_v6.xlsx",
  packetFile: "fulltext/pilot/human_annotation_v6/pilot_150_human_packets_blinded_v6.jsonl",
  validationReport: "fulltext/pilot/human_annotation_v6/results_repaired/pilot_150_human_validation_report_repaired_v6.json",
  builderSource: "code/30_build_pilot_human_adjudication_workbook_v6.mjs",
  output: "fulltext/pilot/human_annotation_v6/adjudication/pilot_150_human_adjudication_109_v6.xlsx",
};

const CORE_FIELDS = [
  "primary_label",
  "relevance_level",
  "evidence_level",
  "af_related_label",
  "af_use_label",
  "adoption_eligible",
  "future_or_hypothetical_only",
  "observed_actions",
];

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

function resolveProject(value) {
  return path.isAbsolute(value) ? value : path.join(PROJECT_ROOT, value);
}

function text(value) {
  if (value === undefined || value === null) return "";
  if (value instanceof Date) return value.toISOString().slice(0, 10);
  return String(value).trim();
}

function asText(value) {
  if (value === undefined || value === null) return "";
  if (Array.isArray(value)) return value.map(asText).filter(Boolean).join(" | ");
  if (typeof value === "object") return JSON.stringify(value);
  return text(value);
}

function canonicalActions(value) {
  const order = [
    "retrieved_precomputed_structure",
    "ran_alphafold",
    "ran_colabfold",
    "integrated_empirical_workflow",
    "docking_or_screening",
    "benchmarked_or_evaluated",
    "modified_or_extended",
    "developed_downstream_tool",
    "discussion_only",
    "none",
  ];
  const selected = new Set(text(value).split("|").map((item) => item.trim()).filter(Boolean));
  return order.filter((item) => selected.has(item)).join("|");
}

async function sha256File(filePath) {
  return crypto.createHash("sha256").update(await fs.readFile(filePath)).digest("hex");
}

async function readJsonl(filePath) {
  return (await fs.readFile(filePath, "utf8"))
    .split(/\r?\n/)
    .filter((line) => line.trim())
    .map((line) => JSON.parse(line));
}

function matrixToObjects(matrix) {
  const headers = matrix[0].map(text);
  return matrix.slice(1).map((row) => Object.fromEntries(headers.map((header, index) => [header, row[index]])));
}

function byReviewId(rows) {
  return new Map(rows.map((row) => [text(row.review_id), row]));
}

function materialAvailability(record) {
  const material = record.input_material || {};
  const quality = record.input_quality || {};
  const abstractUsable = quality.abstract_status === "usable" && Boolean(text(material.abstract));
  const body = (material.evidence_blocks || []).length > 0;
  if (abstractUsable && body) return "abstract + supplied body blocks";
  if (body) return "supplied body blocks only";
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

function styleBody(range) {
  setFont(range, 10);
  range.format.verticalAlignment = "top";
  range.format.wrapText = true;
}

function styleTitle(sheet, title, subtitle, endColumn = "H") {
  sheet.showGridLines = false;
  sheet.getRange("A1").values = [[title]];
  sheet.getRange("A1").format.font = { name: FONT, size: 16, bold: true, color: TEXT };
  sheet.getRange("A2").values = [[subtitle]];
  sheet.getRange("A2").format.font = { name: FONT, size: 10, italic: true, color: MUTED };
  sheet.getRange(`A3:${endColumn}3`).format.borders = { bottom: { style: "thin", color: ACCENT } };
  sheet.getRange("A1:A3").format.rowHeightPx = 24;
}

function addListValidation(sheet, address, values) {
  sheet.getRange(address).dataValidation = {
    rule: { type: "list", values },
  };
}

function setColumnWidths(sheet, widths, rowCount) {
  for (let index = 0; index < widths.length; index += 1) {
    sheet.getRangeByIndexes(0, index, rowCount, 1).format.columnWidthPx = widths[index];
  }
}

function buildInstructions(workbook, rowCount, actionOnlyCount, validationErrors) {
  const sheet = workbook.worksheets.add("Instructions");
  styleTitle(
    sheet,
    "AlphaFold adoption pilot — human adjudication",
    `${rowCount} A/B disagreements; blinded source material only`,
    "H",
  );
  sheet.getRange("A5:B11").values = [
    ["Progress", "Value"],
    ["Records requiring adjudication", rowCount],
    ["Complete", null],
    ["Pending", null],
    ["Action-only disagreements", actionOnlyCount],
    ["Core or multi-field disagreements", rowCount - actionOnlyCount],
    ["Source annotation errors", validationErrors],
  ];
  styleHeader(sheet.getRange("A5:B5"));
  styleBody(sheet.getRange("A6:B11"));
  const finalRow = rowCount + 1;
  sheet.getRange("B7").formulas = [[`=COUNTIF(Adjudication!$AH$2:$AH$${finalRow},"complete")`]];
  sheet.getRange("B8").formulas = [[`=COUNTIF(Adjudication!$AH$2:$AH$${finalRow},"pending")`]];
  sheet.getRange("B6:B11").format.numberFormat = "#,##0";

  const guidance = [
    ["Workflow"],
    ["1. Filter Adjudication by disagreement_fields or status."],
    ["2. Compare the A and B columns. Read A-B Evidence, Paper Text, and Evidence Blocks for the same review_id."],
    ["3. Enter one final value in every yellow adjudicated_* field. The final decision may match A, match B, or use another codebook-valid interpretation."],
    ["4. Enter observed_actions as controlled values separated by |. Keep none alone; keep discussion_only separate from actual-use actions."],
    ["5. Set adjudication_evidence_valid=yes only when the supplied excerpts/material support the final decision."],
    ["6. Enter adjudicator_id, adjudication_date, and concise notes. Set status=complete only after checking all required fields."],
    ["Decision rules"],
    ["R3 is actual downstream use. R4 requires substantive methodological development, modification, systematic benchmarking, or downstream tool development."],
    ["AF use=yes means the study used AF technology or predictions. Adoption=yes means downstream application; original-platform development is use=yes but adoption=no."],
    ["ColabFold execution counts as AF-technology use. Record ran_colabfold alone unless separate evidence establishes an AlphaFold execution."],
    ["E2 is title/abstract evidence. E3 requires attributable evidence in a supplied full-text body block."],
    ["Provenance"],
    ["This workbook contains human A/B annotations and blinded paper material only. Machine-review outputs are not included."],
  ];
  sheet.getRange("D5:D18").values = guidance;
  for (const cell of ["D5", "D12", "D17"]) {
    sheet.getRange(cell).format.fill = "#DCEAF3";
    sheet.getRange(cell).format.font = { name: FONT, size: 10, bold: true, color: TEXT };
  }
  styleBody(sheet.getRange("D5:D18"));
  sheet.getRange("D5:D18").format.rowHeightPx = 42;
  sheet.getRange("A5:B11").format.borders = { bottom: { style: "thin", color: BORDER } };
  setColumnWidths(sheet, [230, 110, 36, 760, 24, 24, 24, 24], 20);
  sheet.freezePanes.freezeRows(3);
  sheet.tabColor = "#2D6A8E";
}

function buildAdjudication(workbook, disagreements) {
  const sheet = workbook.worksheets.add("Adjudication");
  const headers = [
    "adjudication_order", "review_id", "work_id", "title", "disagreement_fields",
    ...CORE_FIELDS.map((field) => `annotator_a_${field}`),
    ...CORE_FIELDS.map((field) => `annotator_b_${field}`),
    "adjudicated_primary_label", "adjudicated_relevance_level", "adjudicated_evidence_level",
    "adjudicated_af_related_label", "adjudicated_af_use_label", "adjudicated_adoption_eligible",
    "adjudicated_future_or_hypothetical_only", "adjudicated_observed_actions",
    "adjudication_evidence_valid", "adjudicator_id", "adjudication_date", "adjudication_notes",
    "adjudication_status",
  ];
  const rows = disagreements.map((row, index) => [
    index + 1,
    text(row.review_id),
    text(row.work_id),
    text(row.title),
    text(row.disagreement_fields),
    ...CORE_FIELDS.map((field) => field === "observed_actions"
      ? canonicalActions(row[`annotator_a_${field}`])
      : text(row[`annotator_a_${field}`])),
    ...CORE_FIELDS.map((field) => field === "observed_actions"
      ? canonicalActions(row[`annotator_b_${field}`])
      : text(row[`annotator_b_${field}`])),
    "", "", "", "", "", "", "", "", "", "", null, "", "pending",
  ]);
  sheet.getRange("A1:AH1").values = [headers];
  sheet.getRange("A2").write(rows);
  sheet.tables.add(`A1:AH${rows.length + 1}`, true, "HumanAdjudicationV6");
  styleHeader(sheet.getRange("A1:AH1"));
  sheet.getRange("A1:AH1").format.rowHeightPx = 54;
  styleBody(sheet.getRange(`A2:AH${rows.length + 1}`));
  sheet.getRange(`A2:AH${rows.length + 1}`).format.rowHeightPx = 62;
  sheet.getRange(`A2:U${rows.length + 1}`).format.fill = SOURCE_FILL;
  sheet.getRange(`V2:AH${rows.length + 1}`).format.fill = INPUT_FILL;
  sheet.getRange(`AF2:AF${rows.length + 1}`).format.numberFormat = "yyyy-mm-dd";

  addListValidation(sheet, `V2:V${rows.length + 1}`, [
    "FP", "background_only", "review_discussion", "database_consumption",
    "model_application", "method_development", "original_platform", "uncertain",
  ]);
  addListValidation(sheet, `W2:W${rows.length + 1}`, ["R0", "R1", "R2", "R3", "R4", "RU"]);
  addListValidation(sheet, `X2:X${rows.length + 1}`, ["E0", "E1", "E2", "E3"]);
  addListValidation(sheet, `Y2:Y${rows.length + 1}`, ["false", "background", "related", "uncertain"]);
  addListValidation(sheet, `Z2:AA${rows.length + 1}`, ["no", "yes", "uncertain"]);
  addListValidation(sheet, `AB2:AB${rows.length + 1}`, ["no", "yes"]);
  addListValidation(sheet, `AD2:AD${rows.length + 1}`, ["no", "yes"]);
  addListValidation(sheet, `AH2:AH${rows.length + 1}`, ["pending", "complete"]);

  const pairs = [["F", "N"], ["G", "O"], ["H", "P"], ["I", "Q"], ["J", "R"], ["K", "S"], ["L", "T"], ["M", "U"]];
  for (const [left, right] of pairs) {
    const formula = `=$${left}2<>$${right}2`;
    const format = { fill: ALERT_FILL, font: { color: ALERT_TEXT, bold: true } };
    sheet.getRange(`${left}2:${left}${rows.length + 1}`).conditionalFormats.addCustom(formula, format);
    sheet.getRange(`${right}2:${right}${rows.length + 1}`).conditionalFormats.addCustom(formula, format);
  }
  sheet.getRange(`AH2:AH${rows.length + 1}`).conditionalFormats.add("containsText", {
    text: "complete", format: { fill: "#D9EAD3", font: { color: "#1B5E20", bold: true } },
  });
  sheet.getRange(`AH2:AH${rows.length + 1}`).conditionalFormats.add("containsText", {
    text: "pending", format: { fill: "#FFF2CC", font: { color: "#7F6000" } },
  });
  sheet.freezePanes.freezeRows(1);
  sheet.freezePanes.freezeColumns(5);
  sheet.tabColor = "#C18B00";
  setColumnWidths(sheet, [
    78, 72, 112, 285, 185,
    145, 70, 70, 92, 75, 82, 90, 260,
    145, 70, 70, 92, 75, 82, 90, 260,
    155, 78, 78, 100, 82, 88, 100, 290,
    110, 105, 100, 300, 88,
  ], rows.length + 1);
  return sheet;
}

function buildAnnotatorEvidence(workbook, disagreements, rowsA, rowsB) {
  const sheet = workbook.worksheets.add("A-B Evidence");
  const headers = [
    "review_id", "work_id", "title", "annotator", "primary_label", "relevance_level",
    "evidence_level", "observed_actions", "action_evidence_map", "exclusion_reason",
    "uncertainty_reasons", "reasoning_summary", "evidence_slot", "source_kind",
    "block_index", "section", "quote", "supports",
  ];
  const mapA = byReviewId(rowsA);
  const mapB = byReviewId(rowsB);
  const rows = [];
  for (const disagreement of disagreements) {
    for (const [annotator, source] of [["A", mapA.get(text(disagreement.review_id))], ["B", mapB.get(text(disagreement.review_id))]]) {
      if (!source) throw new Error(`Missing annotator ${annotator} row for ${disagreement.review_id}`);
      for (let slot = 1; slot <= 3; slot += 1) {
        const fields = ["source_kind", "block_index", "section", "quote", "supports"];
        if (!fields.some((field) => text(source[`evidence_${slot}_${field}`]))) continue;
        rows.push([
          text(disagreement.review_id), text(disagreement.work_id), text(disagreement.title), annotator,
          text(source.primary_label), text(source.relevance_level), text(source.evidence_level),
          canonicalActions(source.observed_actions), text(source.action_evidence_map), text(source.exclusion_reason),
          text(source.uncertainty_reasons), text(source.reasoning_summary), slot,
          text(source[`evidence_${slot}_source_kind`]), text(source[`evidence_${slot}_block_index`]),
          text(source[`evidence_${slot}_section`]), text(source[`evidence_${slot}_quote`]),
          text(source[`evidence_${slot}_supports`]),
        ]);
      }
    }
  }
  sheet.getRange("A1:R1").values = [headers];
  sheet.getRange("A2").write(rows);
  sheet.tables.add(`A1:R${rows.length + 1}`, true, "AnnotatorEvidenceV6");
  styleHeader(sheet.getRange("A1:R1"));
  sheet.getRange("A1:R1").format.rowHeightPx = 50;
  styleBody(sheet.getRange(`A2:R${rows.length + 1}`));
  sheet.getRange(`A2:R${rows.length + 1}`).format.rowHeightPx = 78;
  setColumnWidths(sheet, [72, 112, 280, 65, 140, 72, 72, 260, 230, 150, 180, 360, 72, 100, 75, 150, 520, 180], rows.length + 1);
  sheet.freezePanes.freezeRows(1);
  sheet.freezePanes.freezeColumns(4);
  sheet.tabColor = "#6B879B";
}

function buildPaperText(workbook, disagreements, packetMap) {
  const sheet = workbook.worksheets.add("Paper Text");
  const headers = [
    "review_id", "work_id", "title", "publication_year", "doi", "work_type", "domain_labels",
    "material_available", "abstract_status", "fulltext_body_available", "quality_flags", "abstract",
    "fulltext_source", "packet_sha256",
  ];
  const rows = disagreements.map((row) => {
    const packet = packetMap.get(text(row.review_id));
    if (!packet) throw new Error(`Missing packet for ${row.review_id}`);
    const material = packet.input_material || {};
    const quality = packet.input_quality || {};
    return [
      text(row.review_id), text(row.work_id), text(material.title), material.publication_year ?? null,
      text(material.doi), text(material.work_type), asText(material.domain_labels), materialAvailability(packet),
      text(quality.abstract_status), Boolean(quality.fulltext_body_available), asText(quality.flags),
      quality.abstract_status === "usable" ? text(material.abstract) : "", text(material.fulltext_source),
      text(packet.packet_sha256),
    ];
  });
  sheet.getRange("A1:N1").values = [headers];
  sheet.getRange("A2").write(rows);
  sheet.tables.add(`A1:N${rows.length + 1}`, true, "AdjudicationPaperTextV6");
  styleHeader(sheet.getRange("A1:N1"));
  sheet.getRange("A1:N1").format.rowHeightPx = 50;
  styleBody(sheet.getRange(`A2:N${rows.length + 1}`));
  sheet.getRange(`A2:N${rows.length + 1}`).format.rowHeightPx = 120;
  setColumnWidths(sheet, [72, 112, 300, 82, 205, 105, 160, 180, 115, 120, 170, 680, 130, 360], rows.length + 1);
  sheet.freezePanes.freezeRows(1);
  sheet.freezePanes.freezeColumns(3);
  sheet.tabColor = "#6B879B";
}

function buildEvidenceBlocks(workbook, disagreements, packetMap) {
  const sheet = workbook.worksheets.add("Evidence Blocks");
  const headers = [
    "review_id", "work_id", "source_kind", "block_index", "section", "role",
    "trigger_or_match", "text", "source_ref",
  ];
  const rows = [];
  for (const disagreement of disagreements) {
    const packet = packetMap.get(text(disagreement.review_id));
    const material = packet.input_material || {};
    rows.push([text(disagreement.review_id), text(disagreement.work_id), "title", null, "", "source", "", text(material.title), "title"]);
    if (packet.input_quality?.abstract_status === "usable" && text(material.abstract)) {
      rows.push([text(disagreement.review_id), text(disagreement.work_id), "abstract", null, "Abstract", "source", "", text(material.abstract), "abstract"]);
    }
    for (const reference of material.matched_seed_references || []) {
      rows.push([
        text(disagreement.review_id), text(disagreement.work_id), "matched_reference", null, "References",
        "matched_reference", asText(reference.citation_labels || reference.seed_ids), text(reference.reference_text),
        `matched_reference:${text(reference.reference_id)}`,
      ]);
    }
    for (const block of material.evidence_blocks || []) {
      rows.push([
        text(disagreement.review_id), text(disagreement.work_id), "fulltext_block", block.index ?? null,
        text(block.section), text(block.role), text(block.block_type), text(block.text),
        `fulltext_block:${block.index ?? ""}`,
      ]);
    }
  }
  sheet.getRange("A1:I1").values = [headers];
  sheet.getRange("A2").write(rows);
  sheet.tables.add(`A1:I${rows.length + 1}`, true, "AdjudicationEvidenceBlocksV6");
  styleHeader(sheet.getRange("A1:I1"));
  sheet.getRange("A1:I1").format.rowHeightPx = 48;
  styleBody(sheet.getRange(`A2:I${rows.length + 1}`));
  sheet.getRange(`A2:I${rows.length + 1}`).format.rowHeightPx = 100;
  setColumnWidths(sheet, [72, 112, 115, 78, 170, 110, 180, 720, 160], rows.length + 1);
  sheet.freezePanes.freezeRows(1);
  sheet.freezePanes.freezeColumns(2);
  sheet.tabColor = "#6B879B";
}

function buildCodebook(workbook, sourceWorkbook) {
  const source = sourceWorkbook.worksheets.getItem("Codebook").getRange("A1:F48").values;
  const sheet = workbook.worksheets.add("Codebook");
  sheet.getRange("A1:F48").values = source;
  sheet.showGridLines = false;
  sheet.getRange("A1").format.font = { name: FONT, size: 16, bold: true, color: TEXT };
  sheet.getRange("A2").format.font = { name: FONT, size: 10, italic: true, color: MUTED };
  sheet.getRange("A3:F3").format.borders = { bottom: { style: "thin", color: ACCENT } };
  styleHeader(sheet.getRange("A5:D5"));
  styleHeader(sheet.getRange("F5:F5"));
  styleBody(sheet.getRange("A6:F48"));
  sheet.getRange("A6:F48").format.rowHeightPx = 54;
  setColumnWidths(sheet, [145, 205, 590, 390, 35, 300], 48);
  sheet.freezePanes.freezeRows(5);
  sheet.tabColor = "#2D6A8E";
}

async function buildMetadata(workbook, inputs, rowCount, validationReport) {
  const sheet = workbook.worksheets.add("Metadata");
  styleTitle(sheet, "Reproducibility metadata", "Immutable source identifiers for the human adjudication workbook", "B");
  const orderedReviewIds = inputs.disagreementsRows.map((row) => text(row.review_id)).join("\n");
  const rows = [
    ["field", "value"],
    ["workbook_schema_version", SCHEMA_VERSION],
    ["created_at_utc", `ISO 8601: ${new Date().toISOString()}`],
    ["records_requiring_adjudication", rowCount],
    ["paired_complete_records", validationReport?.agreement?.paired_complete_records ?? ""],
    ["source_annotation_errors", (validationReport?.validation_errors || []).length],
    ["ordered_review_id_sha256", crypto.createHash("sha256").update(orderedReviewIds).digest("hex")],
    ["disagreements_file", path.basename(inputs.disagreements)],
    ["disagreements_sha256", await sha256File(inputs.disagreements)],
    ["annotator_a_file", path.basename(inputs.annotatorA)],
    ["annotator_a_sha256", await sha256File(inputs.annotatorA)],
    ["annotator_b_file", path.basename(inputs.annotatorB)],
    ["annotator_b_sha256", await sha256File(inputs.annotatorB)],
    ["packet_file", path.basename(inputs.packetFile)],
    ["packet_file_sha256", await sha256File(inputs.packetFile)],
    ["validation_report_file", path.basename(inputs.validationReport)],
    ["validation_report_sha256", await sha256File(inputs.validationReport)],
    ["builder_file", path.basename(inputs.builderSource)],
    ["builder_sha256", await sha256File(inputs.builderSource)],
    ["node_version", process.version],
    ["machine_outputs_included", false],
    ["source_workbooks_modified", false],
  ];
  sheet.getRange("A5:B5").values = [rows[0]];
  sheet.getRange("A6").write(rows.slice(1));
  styleHeader(sheet.getRange("A5:B5"));
  styleBody(sheet.getRange(`A6:B${rows.length + 4}`));
  sheet.getRange(`A5:B${rows.length + 4}`).format.borders = { bottom: { style: "thin", color: BORDER } };
  setColumnWidths(sheet, [240, 720], rows.length + 4);
  sheet.freezePanes.freezeRows(5);
  sheet.tabColor = "#7A7A7A";
}

async function renderPreviews(workbook, previewDir) {
  if (!previewDir) return;
  await fs.mkdir(previewDir, { recursive: true });
  const views = [
    ["Instructions", "A1:H18", "instructions"],
    ["Adjudication", "A1:U8", "adjudication_ab"],
    ["Adjudication", "V1:AH8", "adjudication_final"],
    ["A-B Evidence", "A1:R10", "annotator_evidence"],
    ["Paper Text", "A1:N7", "paper_text"],
    ["Evidence Blocks", "A1:I10", "evidence_blocks"],
    ["Codebook", "A1:F48", "codebook"],
    ["Metadata", "A1:B26", "metadata"],
  ];
  for (const [sheetName, range, name] of views) {
    const preview = await workbook.render({ sheetName, range, scale: 1.2, format: "png" });
    await fs.writeFile(path.join(previewDir, `${name}.png`), new Uint8Array(await preview.arrayBuffer()));
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const inputs = {
    disagreements: resolveProject(args.disagreements || DEFAULTS.disagreements),
    annotatorA: resolveProject(args["annotator-a"] || DEFAULTS.annotatorA),
    annotatorB: resolveProject(args["annotator-b"] || DEFAULTS.annotatorB),
    packetFile: resolveProject(args["packet-file"] || DEFAULTS.packetFile),
    validationReport: resolveProject(args["validation-report"] || DEFAULTS.validationReport),
    builderSource: resolveProject(args["builder-source"] || DEFAULTS.builderSource),
    output: resolveProject(args.output || DEFAULTS.output),
  };
  for (const filePath of Object.values(inputs)) {
    if (filePath === inputs.output) continue;
    await fs.access(filePath);
  }
  try {
    await fs.access(inputs.output);
    if (!args.force) throw new Error(`Output exists: ${inputs.output}; pass --force to replace it`);
  } catch (error) {
    if (error.code !== "ENOENT" && !String(error.message).includes("pass --force")) throw error;
    if (String(error.message).includes("pass --force")) throw error;
  }

  const csvWorkbook = await Workbook.fromCSV(await fs.readFile(inputs.disagreements, "utf8"), { sheetName: "Disagreements" });
  const disagreements = matrixToObjects(csvWorkbook.worksheets.getItem("Disagreements").getUsedRange().values);
  if (!disagreements.length) throw new Error("No disagreement rows found");
  inputs.disagreementsRows = disagreements;

  const workbookA = await SpreadsheetFile.importXlsx(await FileBlob.load(inputs.annotatorA));
  const workbookB = await SpreadsheetFile.importXlsx(await FileBlob.load(inputs.annotatorB));
  const rowsA = matrixToObjects(workbookA.worksheets.getItem("Annotations").getRange("A1:AL151").values);
  const rowsB = matrixToObjects(workbookB.worksheets.getItem("Annotations").getRange("A1:AL151").values);
  const packets = await readJsonl(inputs.packetFile);
  const packetMap = new Map(packets.map((packet) => [text(packet.review_id), packet]));
  const validationReport = JSON.parse(await fs.readFile(inputs.validationReport, "utf8"));
  if (validationReport?.agreement?.records_requiring_adjudication !== disagreements.length) {
    throw new Error("Disagreement CSV count does not match validation report");
  }

  const workbook = Workbook.create();
  const actionOnlyCount = disagreements.filter((row) => text(row.disagreement_fields) === "observed_actions").length;
  buildInstructions(workbook, disagreements.length, actionOnlyCount, (validationReport.validation_errors || []).length);
  buildAdjudication(workbook, disagreements);
  buildAnnotatorEvidence(workbook, disagreements, rowsA, rowsB);
  buildPaperText(workbook, disagreements, packetMap);
  buildEvidenceBlocks(workbook, disagreements, packetMap);
  buildCodebook(workbook, workbookA);
  await buildMetadata(workbook, inputs, disagreements.length, validationReport);

  workbook.recalculate();
  const keyCheck = await workbook.inspect({
    kind: "table",
    range: "Instructions!A1:H18",
    include: "values,formulas",
    tableMaxRows: 18,
    tableMaxCols: 8,
    maxChars: 6000,
  });
  console.log(keyCheck.ndjson);
  const errorCheck = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
    options: { useRegex: true, maxResults: 300 },
    summary: "final formula error scan",
  });
  console.log(errorCheck.ndjson);

  await renderPreviews(workbook, args["preview-dir"] ? resolveProject(args["preview-dir"]) : null);
  await fs.mkdir(path.dirname(inputs.output), { recursive: true });
  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(inputs.output);
  const outputSha256 = await sha256File(inputs.output);
  await fs.writeFile(
    `${inputs.output}.sha256`,
    `${outputSha256}  ${path.basename(inputs.output)}\n`,
    "utf8",
  );

  const saved = await SpreadsheetFile.importXlsx(await FileBlob.load(inputs.output));
  const savedCheck = await saved.inspect({
    kind: "table",
    range: "Adjudication!A1:AH6",
    include: "values,formulas",
    tableMaxRows: 6,
    tableMaxCols: 34,
    maxChars: 10000,
  });
  console.log(savedCheck.ndjson);
  console.log(`Adjudication records: ${disagreements.length}`);
  console.log(`Action-only disagreements: ${actionOnlyCount}`);
  console.log(`Core or multi-field disagreements: ${disagreements.length - actionOnlyCount}`);
  console.log(`Workbook written to ${inputs.output}`);
}

main().catch((error) => {
  console.error(error.stack || error.message || String(error));
  process.exitCode = 1;
});
