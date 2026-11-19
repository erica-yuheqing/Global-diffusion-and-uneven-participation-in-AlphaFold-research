#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const PROJECT_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SCHEMA_VERSION = "af-production-direct-human-adjudication-workbook-v1";
const EXPECTED_RECORDS = 187;
const FONT = "Arial";
const HEADER_FILL = "#233B53";
const HEADER_TEXT = "#FFFFFF";
const SOURCE_FILL = "#F3F6F8";
const INPUT_FILL = "#FFF4CC";
const BORDER = "#D5DCE3";
const TEXT = "#1F2933";
const MUTED = "#5B6875";
const ACCENT = "#2D6A8E";
const DEFAULT_QUEUE = "fulltext/production/adjudication_v1/production_direct_human_queue_v1.csv";
const DEFAULT_INPUT = "fulltext/production/model_inputs_v1/full_model_inputs.jsonl";
const DEFAULT_A = "fulltext/production/adjudication_v1/model_a_canonical_valid_v1.jsonl";
const DEFAULT_B = "fulltext/production/adjudication_v1/model_b_canonical_valid_v1.jsonl";
const DEFAULT_OUTPUT = "outputs/production_direct_human_20260915/production_direct_human_adjudication_187_v1.xlsx";

function parseArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) continue;
    const next = argv[index + 1];
    if (next && !next.startsWith("--")) {
      result[token.slice(2)] = next;
      index += 1;
    } else result[token.slice(2)] = true;
  }
  return result;
}

function resolveProject(value) {
  return path.isAbsolute(value) ? value : path.join(PROJECT_ROOT, value);
}

function asText(value) {
  if (value === undefined || value === null) return "";
  if (Array.isArray(value)) return value.map(asText).filter(Boolean).join(" | ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value).trim();
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (quoted) {
      if (char === '"' && text[index + 1] === '"') {
        field += '"';
        index += 1;
      } else if (char === '"') quoted = false;
      else field += char;
    } else if (char === '"') quoted = true;
    else if (char === ",") {
      row.push(field);
      field = "";
    } else if (char === "\n") {
      row.push(field.replace(/\r$/, ""));
      rows.push(row);
      row = [];
      field = "";
    } else field += char;
  }
  if (field || row.length) {
    row.push(field.replace(/\r$/, ""));
    rows.push(row);
  }
  const headers = rows.shift() || [];
  return rows.filter((values) => values.some(Boolean)).map((values) =>
    Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""]))
  );
}

async function readJsonlMap(filePath, wantedIds = null) {
  const result = new Map();
  const lines = (await fs.readFile(filePath, "utf8")).split(/\r?\n/);
  for (const line of lines) {
    if (!line.trim()) continue;
    const value = JSON.parse(line);
    const reviewId = value.review_id;
    if (!reviewId || (wantedIds && !wantedIds.has(reviewId))) continue;
    if (result.has(reviewId)) throw new Error(`Duplicate review_id ${reviewId} in ${filePath}`);
    result.set(reviewId, value);
  }
  return result;
}

async function sha256File(filePath) {
  return crypto.createHash("sha256").update(await fs.readFile(filePath)).digest("hex");
}

function fingerprint(value) {
  return crypto.createHash("sha256")
    .update(JSON.stringify(value, Object.keys(value).sort()))
    .digest("hex");
}

function stableStringify(value) {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
  return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(",")}}`;
}

function packetHash(packet) {
  return crypto.createHash("sha256").update(stableStringify(packet)).digest("hex");
}

function materialAvailability(packet) {
  const material = packet.input_material || {};
  const quality = packet.input_quality || {};
  const hasAbstract = quality.abstract_status === "usable" && Boolean(asText(material.abstract));
  const hasBlocks = (material.evidence_blocks || []).length > 0;
  if (hasAbstract && hasBlocks) return "abstract + supplied body blocks";
  if (hasBlocks) return "supplied body blocks only";
  if (hasAbstract) return "abstract only";
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

function setColumnWidths(sheet, widths, rowCount) {
  widths.forEach((width, index) => {
    sheet.getRangeByIndexes(0, index, rowCount, 1).format.columnWidthPx = width;
  });
}

function addListValidation(sheet, address, values) {
  sheet.getRange(address).dataValidation = { rule: { type: "list", values } };
}

function buildInstructions(workbook, records) {
  const sheet = workbook.worksheets.getItem("Instructions");
  const routeCounts = records.reduce((counts, record) => {
    counts[record.queue.route] = (counts[record.queue.route] || 0) + 1;
    return counts;
  }, {});
  styleTitle(sheet, "Production direct human adjudication", `${records.length} records outside the valid A/B and Model C decision paths`, "H");
  sheet.getRange("A5:B12").values = [
    ["Progress", "Value"],
    ["Records", records.length],
    ["No valid A/B output", routeCounts.direct_human_no_valid_ab || 0],
    ["Oversize context", routeCounts.forced_u_oversize_direct_human || 0],
    ["Complete", null],
    ["Pending", null],
    ["Model/API requests", 0],
    ["Required final decision", records.length],
  ];
  styleHeader(sheet.getRange("A5:B5"));
  styleBody(sheet.getRange("A6:B12"));
  sheet.getRange("B9").formulas = [[`=COUNTIF(Adjudication!$BF$2:$BF$${records.length + 1},"complete")`]];
  sheet.getRange("B10").formulas = [[`=COUNTIF(Adjudication!$BF$2:$BF$${records.length + 1},"pending")`]];
  sheet.getRange("B6:B12").format.numberFormat = "#,##0";

  const guidance = [
    ["Workflow"],
    ["1. Filter Adjudication by route or evidence_tier. Locate the same review_id in Paper Text and Evidence Blocks."],
    ["2. Enter final values only in yellow columns AA:BF. Gray columns are frozen source data."],
    ["3. Supply 1–3 exact excerpts, each no more than 25 whitespace-delimited words, with source_kind, block_index, section, and supports."],
    ["4. observed_actions and human_review_reasons are controlled multi-values separated by |. Keep none alone."],
    ["5. action_evidence_map uses evidence slots, for example ran_colabfold:1 | integrated_empirical_workflow:1,2."],
    ["6. Enter adjudicator_id and date, then set adjudication_status=complete only when every required field is finished."],
    ["Decision boundaries"],
    ["R3 = actual downstream application. R4 = substantive method development, modification, systematic benchmarking, or downstream tool development."],
    ["AF use=yes means the study used AF technology or predictions. Adoption=yes means downstream application. Original AF platform development is use=yes, adoption=no."],
    ["A predicted structure does not prove that the authors ran AlphaFold or ColabFold. Record execution only when supplied text explicitly attributes the run to this study."],
    ["Queue interpretation"],
    ["No valid A/B output means model drafts did not pass validation and are not shown as labels. Oversize context means the deterministic packet exceeded the API token cap and requires human review."],
  ];
  sheet.getRange("D5:D17").values = guidance;
  for (const cell of ["D5", "D12", "D16"]) {
    sheet.getRange(cell).format.fill = "#DCEAF3";
    sheet.getRange(cell).format.font = { name: FONT, size: 10, bold: true, color: TEXT };
  }
  styleBody(sheet.getRange("D5:D17"));
  sheet.getRange("D5:D17").format.rowHeightPx = 46;
  setColumnWidths(sheet, [220, 125, 36, 820, 24, 24, 24, 24], 20);
  sheet.freezePanes.freezeRows(3);
  sheet.tabColor = ACCENT;
}

const FINAL_FIELDS = [
  "adjudicated_primary_label", "adjudicated_relevance_level", "adjudicated_evidence_level",
  "adjudicated_af_related_label", "adjudicated_af_use_label", "adjudicated_adoption_eligible",
  "adjudicated_future_or_hypothetical_only", "adjudicated_observed_actions",
  "adjudicated_action_evidence_map", "adjudicated_exclusion_reason",
  "evidence_1_source_kind", "evidence_1_block_index", "evidence_1_section", "evidence_1_quote", "evidence_1_supports",
  "evidence_2_source_kind", "evidence_2_block_index", "evidence_2_section", "evidence_2_quote", "evidence_2_supports",
  "evidence_3_source_kind", "evidence_3_block_index", "evidence_3_section", "evidence_3_quote", "evidence_3_supports",
  "confidence", "needs_human_review", "human_review_reasons", "reasoning_summary",
  "adjudicator_id", "adjudication_date", "adjudication_status",
];

function sourceRow(record) {
  const packet = record.packet;
  const material = packet.input_material || {};
  const quality = packet.input_quality || {};
  const forced = packet.forced_decision || {};
  return [
    record.order, record.queue.review_id, record.queue.work_id, material.title || "",
    record.queue.route, record.queue.queue_reasons, packet.evidence_tier || "",
    Boolean(packet.model_eligible), materialAvailability(packet), quality.abstract_status || "",
    Boolean(quality.fulltext_body_available), asText(quality.flags), material.publication_year ?? null,
    material.doi || "", material.work_type || "", asText(material.domain_labels),
    asText(packet.context_policy), packet.estimated_input_tokens ?? null,
    forced.primary_label || "", forced.relevance_level || "", forced.evidence_level || "",
    forced.af_related_label || "", forced.af_use_label || "", forced.adoption_eligible || "",
    forced.reason || "", record.input_packet_sha256,
  ];
}

function buildAdjudication(workbook, records) {
  const sheet = workbook.worksheets.getItem("Adjudication");
  const sourceHeaders = [
    "adjudication_order", "review_id", "work_id", "title", "route", "queue_reasons",
    "evidence_tier", "model_eligible", "material_available", "abstract_status",
    "fulltext_body_available", "quality_flags", "publication_year", "doi", "work_type",
    "domain_labels", "context_policy", "estimated_input_tokens", "forced_primary_label",
    "forced_relevance_level", "forced_evidence_level", "forced_af_related_label",
    "forced_af_use_label", "forced_adoption_eligible", "forced_reason", "input_packet_sha256",
  ];
  const headers = [...sourceHeaders, ...FINAL_FIELDS];
  const rows = records.map((record) => [...sourceRow(record), ...Array(30).fill(""), null, "pending"]);
  if (headers.length !== 58 || rows.some((row) => row.length !== 58)) throw new Error("Adjudication matrix must be A:BF");
  sheet.getRange("A1:BF1").values = [headers];
  sheet.getRange("A2").write(rows);
  sheet.tables.add(`A1:BF${rows.length + 1}`, true, "ProductionDirectHumanAdjudicationV1");
  styleHeader(sheet.getRange("A1:BF1"));
  sheet.getRange("A1:BF1").format.rowHeightPx = 58;
  styleBody(sheet.getRange(`A2:BF${rows.length + 1}`));
  sheet.getRange(`A2:BF${rows.length + 1}`).format.rowHeightPx = 72;
  sheet.getRange(`A2:Z${rows.length + 1}`).format.fill = SOURCE_FILL;
  sheet.getRange(`AA2:BF${rows.length + 1}`).format.fill = INPUT_FILL;
  sheet.getRange(`M2:M${rows.length + 1}`).format.numberFormat = "0";
  sheet.getRange(`R2:R${rows.length + 1}`).format.numberFormat = "#,##0";
  sheet.getRange(`AZ2:AZ${rows.length + 1}`).format.numberFormat = "0.00";
  sheet.getRange(`BE2:BE${rows.length + 1}`).format.numberFormat = "yyyy-mm-dd";

  addListValidation(sheet, `AA2:AA${rows.length + 1}`, ["FP", "background_only", "review_discussion", "database_consumption", "model_application", "method_development", "original_platform", "uncertain"]);
  addListValidation(sheet, `AB2:AB${rows.length + 1}`, ["R0", "R1", "R2", "R3", "R4", "RU"]);
  addListValidation(sheet, `AC2:AC${rows.length + 1}`, ["E0", "E1", "E2", "E3"]);
  addListValidation(sheet, `AD2:AD${rows.length + 1}`, ["false", "background", "related", "uncertain"]);
  addListValidation(sheet, `AE2:AF${rows.length + 1}`, ["no", "yes", "uncertain"]);
  addListValidation(sheet, `AG2:AG${rows.length + 1}`, ["false", "true"]);
  addListValidation(sheet, `AJ2:AJ${rows.length + 1}`, ["none", "unrelated_or_abbreviation", "background_only", "review_no_use", "original_platform", "insufficient_evidence", "future_hypothetical_only", "other"]);
  for (const column of ["AK", "AP", "AU"]) addListValidation(sheet, `${column}2:${column}${rows.length + 1}`, ["title", "abstract", "fulltext_block", "matched_reference"]);
  for (const column of ["AO", "AT", "AY"]) addListValidation(sheet, `${column}2:${column}${rows.length + 1}`, ["relation", "use", "engagement", "exclusion", "uncertainty", "relation|use", "relation|engagement", "relation|use|engagement", "relation|uncertainty", "use|engagement"]);
  sheet.getRange(`AZ2:AZ${rows.length + 1}`).dataValidation = { rule: { type: "decimal", operator: "between", formula1: 0, formula2: 1 } };
  addListValidation(sheet, `BA2:BA${rows.length + 1}`, ["false", "true"]);
  addListValidation(sheet, `BF2:BF${rows.length + 1}`, ["pending", "complete"]);
  sheet.getRange(`BF2:BF${rows.length + 1}`).conditionalFormats.add("containsText", { text: "complete", format: { fill: "#D9EAD3", font: { color: "#1B5E20", bold: true } } });
  sheet.getRange(`BF2:BF${rows.length + 1}`).conditionalFormats.add("containsText", { text: "pending", format: { fill: "#FFF2CC", font: { color: "#7F6000" } } });
  sheet.getRange(`E2:E${rows.length + 1}`).conditionalFormats.add("containsText", { text: "oversize", format: { fill: "#FCE8E6", font: { color: "#9C0006", bold: true } } });
  sheet.freezePanes.freezeRows(1);
  sheet.freezePanes.freezeColumns(8);
  sheet.tabColor = "#C18B00";
  setColumnWidths(sheet, [
    75, 118, 118, 300, 210, 180, 150, 95, 200, 120, 130, 180, 90, 210, 110, 160, 330, 110,
    150, 90, 90, 120, 100, 115, 360, 360,
    155, 78, 78, 105, 88, 95, 115, 290, 250, 175,
    120, 85, 170, 400, 190, 120, 85, 170, 400, 190, 120, 85, 170, 400, 190,
    82, 110, 230, 420, 110, 110, 95,
  ], rows.length + 1);
}

function buildPaperText(workbook, records) {
  const sheet = workbook.worksheets.add("Paper Text");
  const headers = ["order", "review_id", "work_id", "title", "publication_year", "doi", "work_type", "domain_labels", "route", "material_available", "abstract_status", "fulltext_body_available", "quality_flags", "abstract", "input_packet_sha256"];
  const rows = records.map((record) => {
    const packet = record.packet;
    const material = packet.input_material || {};
    const quality = packet.input_quality || {};
    return [record.order, record.queue.review_id, record.queue.work_id, material.title || "", material.publication_year ?? null, material.doi || "", material.work_type || "", asText(material.domain_labels), record.queue.route, materialAvailability(packet), quality.abstract_status || "", Boolean(quality.fulltext_body_available), asText(quality.flags), quality.abstract_status === "usable" ? material.abstract || "" : "", record.input_packet_sha256];
  });
  sheet.getRange("A1:O1").values = [headers];
  sheet.getRange("A2").write(rows);
  sheet.tables.add(`A1:O${rows.length + 1}`, true, "ProductionDirectHumanPaperTextV1");
  styleHeader(sheet.getRange("A1:O1"));
  styleBody(sheet.getRange(`A2:O${rows.length + 1}`));
  sheet.getRange(`A2:O${rows.length + 1}`).format.rowHeightPx = 120;
  setColumnWidths(sheet, [70, 118, 118, 300, 82, 210, 110, 160, 210, 190, 120, 125, 180, 680, 360], rows.length + 1);
  sheet.freezePanes.freezeRows(1);
  sheet.freezePanes.freezeColumns(3);
  sheet.tabColor = "#6B879B";
}

function buildEvidenceBlocks(workbook, records) {
  const sheet = workbook.worksheets.add("Evidence Blocks");
  const headers = ["order", "review_id", "work_id", "source_kind", "block_index", "section", "role", "trigger_or_match", "text", "source_ref"];
  const rows = [];
  for (const record of records) {
    const material = record.packet.input_material || {};
    rows.push([record.order, record.queue.review_id, record.queue.work_id, "title", null, "", "source", "", material.title || "", "title"]);
    if (record.packet.input_quality?.abstract_status === "usable" && asText(material.abstract)) rows.push([record.order, record.queue.review_id, record.queue.work_id, "abstract", null, "Abstract", "source", "", material.abstract, "abstract"]);
    for (const reference of material.matched_seed_references || []) rows.push([record.order, record.queue.review_id, record.queue.work_id, "matched_reference", null, "References", "matched_reference", asText(reference.citation_labels || reference.seed_ids), reference.reference_text || "", `matched_reference:${reference.reference_id || ""}`]);
    for (const block of material.evidence_blocks || []) rows.push([record.order, record.queue.review_id, record.queue.work_id, "fulltext_block", block.index ?? null, block.section || "", block.role || "", block.block_type || asText(block.trigger_types), block.text || "", `fulltext_block:${block.index ?? ""}`]);
  }
  sheet.getRange("A1:J1").values = [headers];
  sheet.getRange("A2").write(rows);
  sheet.tables.add(`A1:J${rows.length + 1}`, true, "ProductionDirectHumanEvidenceBlocksV1");
  styleHeader(sheet.getRange("A1:J1"));
  styleBody(sheet.getRange(`A2:J${rows.length + 1}`));
  sheet.getRange(`A2:J${rows.length + 1}`).format.rowHeightPx = 92;
  setColumnWidths(sheet, [70, 118, 118, 125, 85, 190, 110, 210, 720, 170], rows.length + 1);
  sheet.freezePanes.freezeRows(1);
  sheet.freezePanes.freezeColumns(3);
  sheet.tabColor = "#6B879B";
  return rows.length;
}

function buildCodebook(workbook) {
  const sheet = workbook.worksheets.add("Codebook");
  styleTitle(sheet, "Adjudication codebook", "Controlled values remain in English for machine import", "D");
  const rows = [
    ["Category", "Value", "Definition", "Consistency note"],
    ["Primary", "FP", "Confirmed false positive or unrelated AlphaFold abbreviation.", "R0; related=false; use=no; adoption=no."],
    ["Primary", "background_only", "Landmark citation or incidental background mention without substantive discussion or use.", "R1; related=background; use=no; adoption=no."],
    ["Primary", "review_discussion", "Substantive discussion or review without actual use by this study.", "R2; related=related; use=no; adoption=no."],
    ["Primary", "database_consumption", "Obtained or analyzed an existing AFDB or precomputed AF structure.", "R3; use=yes; adoption=yes."],
    ["Primary", "model_application", "Ran AF/ColabFold or integrated/evaluated AF predictions in an empirical workflow.", "R3; use=yes; adoption=yes."],
    ["Primary", "method_development", "Systematic benchmarking, modification, extension, or downstream method/tool development.", "R4; use=yes; adoption=yes."],
    ["Primary", "original_platform", "Original AF model, database, or official platform development.", "R4; use=yes; adoption=no."],
    ["Primary", "uncertain", "Supplied material cannot resolve the primary level.", "Use RU."],
    ["Relevance", "R0", "Confirmed unrelated or false positive.", "Do not use for missing evidence."],
    ["Relevance", "R1", "Background or citation only.", "No actual use."],
    ["Relevance", "R2", "Substantive discussion without study use.", "No actual use."],
    ["Relevance", "R3", "Actual downstream use in an empirical workflow.", "Includes target-specific evaluation and ColabFold use."],
    ["Relevance", "R4", "Substantive method/platform development or systematic methodological contribution.", "Target-specific comparison alone is not automatically R4."],
    ["Relevance", "RU", "R level cannot be assigned reliably.", "Not equivalent to R0."],
    ["Evidence", "E0", "No usable scientific abstract or body evidence.", "Title-only cannot establish actual use."],
    ["Evidence", "E1", "Weak or indirect evidence.", "Cannot establish actual use."],
    ["Evidence", "E2", "Explicit title or abstract evidence supports the decision.", "No body confirmation."],
    ["Evidence", "E3", "Explicit attributable evidence in a supplied full-text body block.", "Bibliography alone is not E3."],
    ["Action", "retrieved_precomputed_structure", "Explicitly obtained an existing AFDB or precomputed model.", "Do not infer from AlphaFold mention alone."],
    ["Action", "ran_alphafold", "Explicit procedure states this study ran AlphaFold.", "Structure origin alone does not prove execution."],
    ["Action", "ran_colabfold", "Explicit procedure states this study ran ColabFold.", "Counts as AF technology use."],
    ["Action", "integrated_empirical_workflow", "Used AF prediction for interpretation, fitting, docking, screening, or empirical analysis.", "Cryo-EM map fitting belongs here."],
    ["Action", "docking_or_screening", "Molecular, ligand, or PPI docking or virtual screening using an AF prediction.", "Not rigid fitting into density."],
    ["Action", "benchmarked_or_evaluated", "Actually evaluated prediction accuracy, quality, confidence, failures, or limitations.", "May occur in R3 or R4."],
    ["Action", "modified_or_extended", "Explicit AF method modification or extension.", "Requires direct evidence."],
    ["Action", "developed_downstream_tool", "Developed a downstream tool or method materially using AF outputs.", "Requires direct evidence."],
    ["Action", "discussion_only", "Substantive AF discussion without actual use.", "Cannot coexist with actual-use action."],
    ["Action", "none", "No supported observed action.", "Cannot coexist with another action."],
    ["Uncertainty", "prediction_origin_unclear", "Prediction was used, but execution versus retrieval is unclear.", "Retain supported use; omit unproven run."],
    ["Uncertainty", "abstract_only", "Actual-use decision relies only on title or abstract evidence.", "Use | for multiple reasons."],
    ["Uncertainty", "boundary_R2_R3", "Discussion versus actual use is unresolved.", "Requires human judgment."],
    ["Uncertainty", "boundary_R3_R4", "Application versus method contribution is unresolved.", "Requires human judgment."],
    ["Uncertainty", "insufficient_evidence", "Supplied evidence cannot support a stable decision.", "Use uncertain/RU where appropriate."],
  ];
  sheet.getRange("A5:D5").values = [rows[0]];
  sheet.getRange("A6").write(rows.slice(1));
  styleHeader(sheet.getRange("A5:D5"));
  styleBody(sheet.getRange(`A6:D${rows.length + 4}`));
  sheet.getRange(`A5:D${rows.length + 4}`).format.borders = { bottom: { style: "thin", color: BORDER } };
  sheet.getRange(`A6:D${rows.length + 4}`).format.rowHeightPx = 54;
  setColumnWidths(sheet, [140, 210, 590, 390], rows.length + 4);
  sheet.freezePanes.freezeRows(5);
  sheet.tabColor = ACCENT;
}

async function buildMetadata(workbook, inputs, records, evidenceRows) {
  const sheet = workbook.worksheets.add("Metadata");
  styleTitle(sheet, "Reproducibility metadata", "Immutable source identifiers for this adjudication workbook", "B");
  const routeCounts = records.reduce((counts, record) => {
    counts[record.queue.route] = (counts[record.queue.route] || 0) + 1;
    return counts;
  }, {});
  const rows = [
    ["field", "value"],
    ["workbook_schema_version", SCHEMA_VERSION],
    ["created_at_utc", `ISO 8601: ${new Date().toISOString()}`],
    ["record_count", records.length],
    ["direct_human_no_valid_ab", routeCounts.direct_human_no_valid_ab || 0],
    ["forced_u_oversize_direct_human", routeCounts.forced_u_oversize_direct_human || 0],
    ["evidence_block_rows", evidenceRows],
    ["queue_file", path.relative(PROJECT_ROOT, inputs.queue)],
    ["queue_file_sha256", await sha256File(inputs.queue)],
    ["frozen_input_file", path.relative(PROJECT_ROOT, inputs.input)],
    ["frozen_input_file_sha256", await sha256File(inputs.input)],
    ["model_a_canonical_file", path.relative(PROJECT_ROOT, inputs.modelA)],
    ["model_a_canonical_file_sha256", await sha256File(inputs.modelA)],
    ["model_b_canonical_file", path.relative(PROJECT_ROOT, inputs.modelB)],
    ["model_b_canonical_file_sha256", await sha256File(inputs.modelB)],
    ["builder_file", path.relative(PROJECT_ROOT, inputs.builder)],
    ["builder_sha256", await sha256File(inputs.builder)],
    ["provider_or_model_requests_made_by_builder", 0],
    ["invalid_a_b_drafts_presented_as_labels", false],
    ["node_version", process.version],
  ];
  sheet.getRange("A5:B5").values = [rows[0]];
  sheet.getRange("A6").write(rows.slice(1));
  styleHeader(sheet.getRange("A5:B5"));
  styleBody(sheet.getRange(`A6:B${rows.length + 4}`));
  setColumnWidths(sheet, [300, 820], rows.length + 4);
  sheet.freezePanes.freezeRows(5);
  sheet.tabColor = "#777777";
}

async function renderPreviews(workbook, previewDir) {
  await fs.mkdir(previewDir, { recursive: true });
  const views = [
    ["Instructions", "A1:H17", "instructions"],
    ["Adjudication", "A1:Z7", "adjudication_sources"],
    ["Adjudication", "AA1:BF7", "adjudication_inputs"],
    ["Paper Text", "A1:O6", "paper_text"],
    ["Evidence Blocks", "A1:J9", "evidence_blocks"],
    ["Codebook", "A1:D38", "codebook"],
    ["Metadata", "A1:B25", "metadata"],
  ];
  for (const [sheetName, range, name] of views) {
    const blob = await workbook.render({ sheetName, range, scale: 1, format: "png" });
    await fs.writeFile(path.join(previewDir, `${name}.png`), new Uint8Array(await blob.arrayBuffer()));
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const inputs = {
    queue: resolveProject(args.queue || DEFAULT_QUEUE),
    input: resolveProject(args.input || DEFAULT_INPUT),
    modelA: resolveProject(args["model-a"] || DEFAULT_A),
    modelB: resolveProject(args["model-b"] || DEFAULT_B),
    output: resolveProject(args.output || DEFAULT_OUTPUT),
    builder: fileURLToPath(import.meta.url),
  };
  for (const key of ["queue", "input", "modelA", "modelB"]) await fs.access(inputs[key]);
  if (!args.force) {
    try { await fs.access(inputs.output); throw new Error(`Output exists: ${inputs.output}; pass --force to replace it`); }
    catch (error) { if (error.code !== "ENOENT") throw error; }
  }

  const queue = parseCsv(await fs.readFile(inputs.queue, "utf8"));
  if (queue.length !== EXPECTED_RECORDS) throw new Error(`Expected ${EXPECTED_RECORDS} queue records, found ${queue.length}`);
  const ids = new Set(queue.map((row) => row.review_id));
  if (ids.size !== EXPECTED_RECORDS) throw new Error("Duplicate review_id in direct-human queue");
  if (queue.some((row) => row.review_id !== row.work_id)) throw new Error("Queue review_id/work_id mismatch");
  const routeCounts = queue.reduce((counts, row) => {
    counts[row.route] = (counts[row.route] || 0) + 1;
    return counts;
  }, {});
  if (routeCounts.direct_human_no_valid_ab !== 178 || routeCounts.forced_u_oversize_direct_human !== 9) {
    throw new Error(`Unexpected route counts: ${JSON.stringify(routeCounts)}`);
  }

  const packets = await readJsonlMap(inputs.input, ids);
  if (packets.size !== EXPECTED_RECORDS) throw new Error(`Frozen packets found ${packets.size}/${EXPECTED_RECORDS}`);
  const modelA = await readJsonlMap(inputs.modelA, ids);
  const modelB = await readJsonlMap(inputs.modelB, ids);
  if (modelA.size || modelB.size) throw new Error(`Direct-human queue unexpectedly overlaps canonical A/B: A=${modelA.size}, B=${modelB.size}`);

  const records = queue.map((row, index) => {
    const packet = packets.get(row.review_id);
    if (!packet || packet.work_id !== row.work_id) throw new Error(`Packet identity mismatch for ${row.review_id}`);
    return { order: index + 1, queue: row, packet, input_packet_sha256: packetHash(packet) };
  });

  const workbook = Workbook.create();
  workbook.worksheets.add("Adjudication");
  workbook.worksheets.add("Instructions");
  buildInstructions(workbook, records);
  buildAdjudication(workbook, records);
  buildPaperText(workbook, records);
  const evidenceRows = buildEvidenceBlocks(workbook, records);
  buildCodebook(workbook);
  await buildMetadata(workbook, inputs, records, evidenceRows);
  workbook.recalculate();

  const check = await workbook.inspect({ kind: "table", range: "Instructions!A1:H17", include: "values,formulas", tableMaxRows: 17, tableMaxCols: 8, maxChars: 7000 });
  console.log(check.ndjson);
  const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 300 }, summary: "final formula error scan" });
  console.log(errors.ndjson);

  const previewDir = resolveProject(args["preview-dir"] || `${path.dirname(path.relative(PROJECT_ROOT, inputs.output))}/previews`);
  await renderPreviews(workbook, previewDir);
  await fs.mkdir(path.dirname(inputs.output), { recursive: true });
  const blob = await SpreadsheetFile.exportXlsx(workbook);
  await blob.save(inputs.output);
  const outputHash = await sha256File(inputs.output);
  await fs.writeFile(`${inputs.output}.sha256`, `${outputHash}  ${path.basename(inputs.output)}\n`, "ascii");

  const saved = await SpreadsheetFile.importXlsx(await FileBlob.load(inputs.output));
  const savedCheck = await saved.inspect({ kind: "table", range: "Adjudication!A1:BF5", include: "values,formulas", tableMaxRows: 5, tableMaxCols: 58, maxChars: 16000 });
  console.log(savedCheck.ndjson);
  const savedErrors = await saved.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 300 }, summary: "saved workbook formula error scan" });
  console.log(savedErrors.ndjson);
  console.log(`Adjudication records: ${records.length}`);
  console.log(`Route counts: ${JSON.stringify(routeCounts)}`);
  console.log(`Evidence block rows: ${evidenceRows}`);
  console.log(`Workbook written to ${inputs.output}`);
  console.log(`Previews written to ${previewDir}`);
}

main().catch((error) => {
  console.error(error.stack || error.message || String(error));
  process.exitCode = 1;
});
