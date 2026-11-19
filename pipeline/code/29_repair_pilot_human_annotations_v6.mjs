#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const RULESET_VERSION = "af-human-annotation-repair-v6-2026-09-10-r2";
const VALID_SUPPORTS = ["relation", "use", "engagement", "exclusion", "uncertainty"];
const VALID_SUPPORT_SET = new Set(VALID_SUPPORTS);
const SUPPORT_COMBINATIONS = [];
for (let size = 1; size <= VALID_SUPPORTS.length; size += 1) {
  const visit = (start, chosen) => {
    if (chosen.length === size) {
      SUPPORT_COMBINATIONS.push(chosen.join("|"));
      return;
    }
    for (let index = start; index < VALID_SUPPORTS.length; index += 1) {
      visit(index + 1, [...chosen, VALID_SUPPORTS[index]]);
    }
  };
  visit(0, []);
}
const ACTUAL_USE_ACTIONS = new Set([
  "retrieved_precomputed_structure",
  "ran_alphafold",
  "ran_colabfold",
  "integrated_empirical_workflow",
  "docking_or_screening",
  "benchmarked_or_evaluated",
  "modified_or_extended",
  "developed_downstream_tool",
]);
const METHOD_ACTIONS = new Set([
  "integrated_empirical_workflow",
  "docking_or_screening",
  "benchmarked_or_evaluated",
  "modified_or_extended",
  "developed_downstream_tool",
]);
const UNCERTAINTY_TOKENS = new Set([
  "abstract_only",
  "insufficient_evidence",
  "boundary_R2_R3",
  "boundary_R3_R4",
  "original_vs_downstream",
  "conflicting_evidence",
  "citation_link_uncertain",
  "prediction_origin_unclear",
  "input_quality",
  "other",
]);
const EXCLUSION_TOKENS = new Set([
  "unrelated_or_abbreviation",
  "background_only",
  "review_no_use",
  "future_hypothetical_only",
]);

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

function text(value) {
  if (value === undefined || value === null) return "";
  return String(value).trim();
}

function splitPipe(value) {
  return [...new Set(text(value).split("|").map((item) => item.trim()).filter(Boolean))];
}

function canonicalSupports(values) {
  const chosen = new Set(values);
  return VALID_SUPPORTS.filter((value) => chosen.has(value)).join("|");
}

function containsAfTerm(value) {
  return /alpha\s*fold|colabfold|afdb/i.test(text(value));
}

function parseActionEvidenceMap(value) {
  const result = new Map();
  for (const item of splitPipe(value)) {
    const separator = item.indexOf(":");
    if (separator < 0) continue;
    const action = item.slice(0, separator).trim();
    const indices = item
      .slice(separator + 1)
      .split(",")
      .map((raw) => Number(raw.trim()))
      .filter((number) => Number.isInteger(number) && number >= 1 && number <= 3);
    result.set(action, new Set(indices));
  }
  return result;
}

function fallbackSupports(row, quote, mappedActions) {
  const result = new Set(["relation"]);
  const primary = text(row.primary_label);
  const relevance = text(row.relevance_level);
  const use = text(row.af_use_label);
  const exclusion = text(row.exclusion_reason);
  const uncertainty = splitPipe(row.uncertainty_reasons);
  if (use === "yes") result.add("use");
  if (
    relevance === "R3" ||
    relevance === "R4" ||
    [...mappedActions].some((action) => ACTUAL_USE_ACTIONS.has(action))
  ) {
    result.add("engagement");
  }
  if (
    primary === "FP" ||
    primary === "background_only" ||
    primary === "review_discussion" ||
    primary === "original_platform" ||
    (exclusion && exclusion !== "none")
  ) {
    result.add("exclusion");
  }
  if (primary === "uncertain" || relevance === "RU" || uncertainty.length > 0) {
    result.add("uncertainty");
  }
  if (!containsAfTerm(quote) && result.size > 1) result.delete("relation");
  if (result.size === 0) result.add("uncertainty");
  return result;
}

function normalizeSupportCell(currentValue, row, quote, evidenceSlot) {
  const tokens = splitPipe(currentValue);
  if (tokens.length > 0 && tokens.every((token) => VALID_SUPPORT_SET.has(token))) {
    return {
      value: canonicalSupports(tokens),
      rule: "canonicalize_existing_supports",
      confirmationRequired: false,
    };
  }

  const actionMap = parseActionEvidenceMap(row.action_evidence_map);
  const mappedActions = new Set(
    [...actionMap.entries()]
      .filter(([, indices]) => indices.has(evidenceSlot))
      .map(([action]) => action),
  );
  const result = new Set();
  let genericClassification = false;
  for (const token of tokens) {
    if (token === "classification") {
      genericClassification = true;
      continue;
    }
    if (token === "context" || token === "discussion_only") result.add("relation");
    if (ACTUAL_USE_ACTIONS.has(token)) result.add("use");
    if (METHOD_ACTIONS.has(token)) result.add("engagement");
    if (UNCERTAINTY_TOKENS.has(token)) result.add("uncertainty");
    if (EXCLUSION_TOKENS.has(token)) result.add("exclusion");
    if (token === "original_platform") {
      result.add("relation");
      result.add("use");
      result.add("engagement");
      result.add("exclusion");
    }
  }
  for (const action of mappedActions) {
    if (ACTUAL_USE_ACTIONS.has(action)) result.add("use");
    if (METHOD_ACTIONS.has(action)) result.add("engagement");
    if (action === "discussion_only") result.add("relation");
  }
  if (containsAfTerm(quote)) result.add("relation");

  if (genericClassification || result.size === 0) {
    for (const support of fallbackSupports(row, quote, mappedActions)) result.add(support);
  }
  if (result.size === 0) {
    throw new Error(`Unable to normalize supports for ${row.review_id} evidence ${evidenceSlot}`);
  }
  return {
    value: canonicalSupports(result),
    rule: genericClassification
      ? "derive_generic_classification_supports"
      : "map_annotator_terms_to_support_dimensions",
    confirmationRequired: genericClassification,
  };
}

function csvCell(value) {
  const raw = value === undefined || value === null ? "" : String(value);
  return /[",\r\n]/.test(raw) ? `"${raw.replaceAll('"', '""')}"` : raw;
}

function toCsv(rows, headers) {
  return [headers, ...rows.map((row) => headers.map((header) => row[header] ?? ""))]
    .map((row) => row.map(csvCell).join(","))
    .join("\n") + "\n";
}

async function sha256File(filePath) {
  return crypto.createHash("sha256").update(await fs.readFile(filePath)).digest("hex");
}

async function saveBlob(blob, filePath) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, new Uint8Array(await blob.arrayBuffer()));
}

async function renderSource(workbook, annotator, previewDir) {
  const preview = await workbook.render({
    sheetName: "Annotations",
    range: "P1:AH10",
    scale: 1,
    format: "png",
  });
  const target = path.join(previewDir, `annotator_${annotator}_before.png`);
  await saveBlob(preview, target);
  return target;
}

function rowObjects(matrix, headers) {
  return matrix.slice(1).map((values) =>
    Object.fromEntries(headers.map((header, index) => [header, values[index]])),
  );
}

function addChange(changes, annotator, rowNumber, row, cell, field, oldValue, newValue, rule, confirmationRequired) {
  if (text(oldValue) === text(newValue)) return;
  changes.push({
    annotator,
    assignment_order: row.assignment_order,
    reviewer_record_id: row.reviewer_record_id,
    review_id: row.review_id,
    work_id: row.work_id,
    cell,
    field,
    old_value: text(oldValue),
    new_value: text(newValue),
    rule_id: rule,
    human_confirmation_required: confirmationRequired ? "yes" : "no",
  });
}

async function repairWorkbook(inputPath, outputPath, annotator, previewDir, changes) {
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
  const sheet = workbook.worksheets.getItem("Annotations");
  const matrix = sheet.getRange("A1:AL151").values;
  const headers = matrix[0].map(text);
  const rows = rowObjects(matrix, headers);
  const columnIndex = Object.fromEntries(headers.map((header, index) => [header, index]));
  const supportFields = ["evidence_1_supports", "evidence_2_supports", "evidence_3_supports"];
  const supportColumns = ["W", "AB", "AG"];
  const quoteFields = ["evidence_1_quote", "evidence_2_quote", "evidence_3_quote"];

  for (let rowOffset = 0; rowOffset < rows.length; rowOffset += 1) {
    const row = rows[rowOffset];
    const rowNumber = rowOffset + 2;
    for (let slotOffset = 0; slotOffset < 3; slotOffset += 1) {
      const field = supportFields[slotOffset];
      const quoteField = quoteFields[slotOffset];
      if (!text(row[quoteField])) continue;
      const normalized = normalizeSupportCell(row[field], row, row[quoteField], slotOffset + 1);
      addChange(
        changes,
        annotator,
        rowNumber,
        row,
        `${supportColumns[slotOffset]}${rowNumber}`,
        field,
        row[field],
        normalized.value,
        normalized.rule,
        normalized.confirmationRequired,
      );
      matrix[rowOffset + 1][columnIndex[field]] = normalized.value;
      row[field] = normalized.value;
    }

    if (annotator === "A" && splitPipe(row.observed_actions).join("|") === "none" && text(row.action_evidence_map)) {
      addChange(
        changes,
        annotator,
        rowNumber,
        row,
        `Q${rowNumber}`,
        "action_evidence_map",
        row.action_evidence_map,
        "",
        "clear_action_map_for_none",
        false,
      );
      matrix[rowOffset + 1][columnIndex.action_evidence_map] = null;
      row.action_evidence_map = null;
    }

    if (
      annotator === "B" &&
      text(row.evidence_level) === "E2" &&
      text(row.af_use_label) === "yes" &&
      !splitPipe(row.uncertainty_reasons).includes("abstract_only")
    ) {
      const next = [...splitPipe(row.uncertainty_reasons), "abstract_only"].join("|");
      addChange(
        changes,
        annotator,
        rowNumber,
        row,
        `AH${rowNumber}`,
        "uncertainty_reasons",
        row.uncertainty_reasons,
        next,
        "add_abstract_only_for_E2_actual_use",
        false,
      );
      matrix[rowOffset + 1][columnIndex.uncertainty_reasons] = next;
      row.uncertainty_reasons = next;
    }

    if (annotator === "A" && text(row.review_id) === "P062") {
      addChange(
        changes,
        annotator,
        rowNumber,
        row,
        `R${rowNumber}`,
        "exclusion_reason",
        row.exclusion_reason,
        "review_no_use",
        "align_review_discussion_exclusion_reason",
        true,
      );
      matrix[rowOffset + 1][columnIndex.exclusion_reason] = "review_no_use";
      row.exclusion_reason = "review_no_use";
    }
  }

  sheet.getRange("Q2:Q151").values = matrix.slice(1).map((row) => [row[columnIndex.action_evidence_map]]);
  sheet.getRange("R2:R151").values = matrix.slice(1).map((row) => [row[columnIndex.exclusion_reason]]);
  sheet.getRange("W2:W151").values = matrix.slice(1).map((row) => [row[columnIndex.evidence_1_supports]]);
  sheet.getRange("AB2:AB151").values = matrix.slice(1).map((row) => [row[columnIndex.evidence_2_supports]]);
  sheet.getRange("AG2:AG151").values = matrix.slice(1).map((row) => [row[columnIndex.evidence_3_supports]]);
  sheet.getRange("AH2:AH151").values = matrix.slice(1).map((row) => [row[columnIndex.uncertainty_reasons]]);
  const instructions = workbook.worksheets.getItem("Instructions");
  const instructionRange = instructions.getRange("A1:H29");
  const instructionValues = instructionRange.values;
  for (let row = 0; row < instructionValues.length; row += 1) {
    for (let column = 0; column < instructionValues[row].length; column += 1) {
      const current = text(instructionValues[row][column]);
      if (current.startsWith("5. Separate multiple observed_actions")) {
        instructionValues[row][column] =
          "5. Separate multiple observed_actions and uncertainty_reasons with |. Use action_evidence_map such as ran_alphafold:1 | integrated_empirical_workflow:1,2. For evidence_*_supports choose a legal single- or multi-value combination from the dropdown.";
      }
    }
  }
  instructionRange.values = instructionValues;

  const codebook = workbook.worksheets.getItem("Codebook");
  codebook.getRange("A44:D48").values = [
    ["Evidence support", "relation", "The excerpt supports the AlphaFold relationship decision.", "May support false, background, related, or uncertain relation classification."],
    ["Evidence support", "use", "The excerpt supports actual use of AlphaFold technology or outputs by this study.", "Do not use for background citations or hypothetical use."],
    ["Evidence support", "engagement", "The excerpt supports the depth or form of methodological or downstream engagement.", "Use for action, R3/R4 boundary, benchmarking, modification, or tool-development evidence."],
    ["Evidence support", "exclusion", "The excerpt supports exclusion from actual downstream adoption.", "Includes false positive, background/review only, original platform, or future-only evidence."],
    ["Evidence support", "uncertainty", "The excerpt supports a material uncertainty or evidence limitation.", "Link to an uncertainty reason when applicable."],
  ];
  codebook.getRange("A44:D48").format = {
    font: { name: "Arial", size: 10, color: "#1F2933" },
    fill: "#FFFFFF",
    wrapText: true,
    verticalAlignment: "center",
    borders: { bottom: { style: "thin", color: "#D5DCE3" } },
  };
  codebook.getRange("A44:D48").format.rowHeightPx = 56;
  codebook.getRange("F5").values = [["Valid evidence-support combinations"]];
  codebook.getRange("F5").format = {
    fill: "#233B53",
    font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" },
    wrapText: true,
    verticalAlignment: "center",
    horizontalAlignment: "center",
    borders: { preset: "outside", style: "thin", color: "#D5DCE3" },
  };
  codebook.getRange("F6:F36").values = SUPPORT_COMBINATIONS.map((value) => [value]);
  codebook.getRange("F6:F36").format = {
    font: { name: "Arial", size: 10, color: "#1F2933" },
    fill: "#FFFFFF",
    verticalAlignment: "center",
    borders: { bottom: { style: "thin", color: "#D5DCE3" } },
  };
  codebook.getRange("F5:F36").format.columnWidthPx = 300;
  codebook.getRange("F5").format.rowHeightPx = 42;
  codebook.getRange("F6:F36").format.rowHeightPx = 24;
  for (const column of supportColumns) {
    sheet.getRange(`${column}2:${column}151`).dataValidation = {
      rule: { type: "list", formula1: "Codebook!$F$6:$F$36" },
    };
  }

  workbook.recalculate();
  const formulaErrors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
    options: { useRegex: true, maxResults: 100 },
    summary: `formula error scan for annotator ${annotator}`,
  });
  const repairInspect = await workbook.inspect({
    kind: "table",
    range: "Annotations!P1:AH10",
    include: "values,formulas",
    tableMaxRows: 10,
    tableMaxCols: 19,
    maxChars: 12000,
  });
  console.log(`Annotator ${annotator} formula scan: ${formulaErrors.ndjson}`);
  console.log(`Annotator ${annotator} repair inspect: ${repairInspect.ndjson}`);

  const preview = await workbook.render({
    sheetName: "Annotations",
    range: "P1:AH10",
    scale: 1,
    format: "png",
  });
  await saveBlob(preview, path.join(previewDir, `annotator_${annotator}_after.png`));

  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  const temporaryPath = path.join(path.dirname(outputPath), `.${path.basename(outputPath)}.${process.pid}.writing.xlsx`);
  const exported = await SpreadsheetFile.exportXlsx(workbook);
  await exported.save(temporaryPath);
  await fs.rename(temporaryPath, outputPath);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args["annotator-a"] || !args["annotator-b"] || !args["output-dir"] || !args["preview-dir"]) {
    throw new Error("Required: --annotator-a A.xlsx --annotator-b B.xlsx --output-dir DIR --preview-dir DIR");
  }
  const inputs = {
    A: path.resolve(args["annotator-a"]),
    B: path.resolve(args["annotator-b"]),
  };
  const outputDir = path.resolve(args["output-dir"]);
  const previewDir = path.resolve(args["preview-dir"]);
  await fs.mkdir(previewDir, { recursive: true });

  if (args["inspect-only"]) {
    for (const annotator of ["A", "B"]) {
      const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputs[annotator]));
      const inspection = await workbook.inspect({
        kind: "table",
        range: "Annotations!P1:AH10",
        include: "values,formulas",
        tableMaxRows: 10,
        tableMaxCols: 19,
        maxChars: 12000,
      });
      console.log(`Annotator ${annotator} source inspect: ${inspection.ndjson}`);
      console.log(`Annotator ${annotator} preview: ${await renderSource(workbook, annotator, previewDir)}`);
      const codebookPreview = await workbook.render({
        sheetName: "Codebook",
        range: "A1:F48",
        scale: 1,
        format: "png",
      });
      const codebookTarget = path.join(previewDir, `annotator_${annotator}_codebook_before.png`);
      await saveBlob(codebookPreview, codebookTarget);
      console.log(`Annotator ${annotator} codebook preview: ${codebookTarget}`);
    }
    return;
  }

  const outputs = {
    A: path.join(outputDir, "pilot_150_annotator_A_repaired_v6.xlsx"),
    B: path.join(outputDir, "pilot_150_annotator_B_repaired_v6.xlsx"),
  };
  for (const output of Object.values(outputs)) {
    try {
      await fs.access(output);
      if (!args.force) throw new Error(`Output exists: ${output}; pass --force to replace it`);
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
    }
  }

  const changes = [];
  for (const annotator of ["A", "B"]) {
    await repairWorkbook(inputs[annotator], outputs[annotator], annotator, previewDir, changes);
  }

  const auditHeaders = [
    "annotator",
    "assignment_order",
    "reviewer_record_id",
    "review_id",
    "work_id",
    "cell",
    "field",
    "old_value",
    "new_value",
    "rule_id",
    "human_confirmation_required",
  ];
  const auditPath = path.join(outputDir, "pilot_150_repair_changes_v6.csv");
  const reviewPath = path.join(outputDir, "pilot_150_repair_review_queue_v6.csv");
  await fs.writeFile(auditPath, toCsv(changes, auditHeaders), "utf8");
  await fs.writeFile(
    reviewPath,
    toCsv(changes.filter((change) => change.human_confirmation_required === "yes"), auditHeaders),
    "utf8",
  );

  const sourceHashes = Object.fromEntries(
    await Promise.all(Object.entries(inputs).map(async ([key, value]) => [key, await sha256File(value)])),
  );
  const outputHashes = Object.fromEntries(
    await Promise.all(Object.entries(outputs).map(async ([key, value]) => [key, await sha256File(value)])),
  );
  const countsByRule = {};
  for (const change of changes) countsByRule[change.rule_id] = (countsByRule[change.rule_id] || 0) + 1;
  const manifest = {
    schema_version: "af-human-annotation-workbook-repair-manifest-v1",
    ruleset_version: RULESET_VERSION,
    created_at_utc: new Date().toISOString(),
    implementation_file: path.basename(fileURLToPath(import.meta.url)),
    implementation_sha256: await sha256File(fileURLToPath(import.meta.url)),
    source_files: {
      A: { path: inputs.A, sha256: sourceHashes.A },
      B: { path: inputs.B, sha256: sourceHashes.B },
    },
    output_files: {
      A: { path: outputs.A, sha256: outputHashes.A },
      B: { path: outputs.B, sha256: outputHashes.B },
    },
    audit_file: { path: auditPath, sha256: await sha256File(auditPath) },
    review_queue_file: { path: reviewPath, sha256: await sha256File(reviewPath) },
    change_count: changes.length,
    human_confirmation_change_count: changes.filter(
      (change) => change.human_confirmation_required === "yes",
    ).length,
    counts_by_rule: countsByRule,
    supports_dropdown: {
      source_range: "Codebook!F6:F36",
      combination_count: SUPPORT_COMBINATIONS.length,
      values: VALID_SUPPORTS,
      permits_pipe_delimited_combinations: true,
    },
    method_note:
      "Original workbooks were not modified. Controlled-vocabulary repairs preserve the original labels and quotes. Generic B support values were derived from the annotator's existing structured decisions and remain in the human-confirmation queue.",
  };
  const manifestPath = path.join(outputDir, "pilot_150_repair_manifest_v6.json");
  await fs.writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  for (const output of [...Object.values(outputs), auditPath, reviewPath, manifestPath]) {
    await fs.writeFile(`${output}.sha256`, `${await sha256File(output)}  ${path.basename(output)}\n`, "utf8");
  }

  console.log(`Repair changes: ${changes.length}`);
  console.log(`Human-confirmation changes: ${manifest.human_confirmation_change_count}`);
  console.log(`Counts by rule: ${JSON.stringify(countsByRule)}`);
  console.log(`Annotator A output: ${outputs.A}`);
  console.log(`Annotator B output: ${outputs.B}`);
  console.log(`Audit: ${auditPath}`);
  console.log(`Review queue: ${reviewPath}`);
  console.log(`Manifest: ${manifestPath}`);
}

main().catch((error) => {
  console.error(error.stack || error.message || String(error));
  process.exitCode = 1;
});
