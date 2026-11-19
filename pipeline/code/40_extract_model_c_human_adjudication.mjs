#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const EXPECTED_HEADERS = [
  "adjudication_order", "review_id", "work_id", "title", "source_batch",
  "failure_categories", "validation_errors", "evidence_tier",
  "model_a_status", "model_a_primary_label", "model_a_relevance_level", "model_a_evidence_level",
  "model_a_af_related_label", "model_a_af_use_label", "model_a_adoption_eligible",
  "model_a_future_or_hypothetical_only", "model_a_observed_actions",
  "model_b_status", "model_b_primary_label", "model_b_relevance_level", "model_b_evidence_level",
  "model_b_af_related_label", "model_b_af_use_label", "model_b_adoption_eligible",
  "model_b_future_or_hypothetical_only", "model_b_observed_actions",
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

function text(value) {
  if (value === undefined || value === null) return "";
  if (value instanceof Date) return value.toISOString().slice(0, 10);
  return String(value).trim();
}

async function sha256File(filePath) {
  return crypto.createHash("sha256").update(await fs.readFile(filePath)).digest("hex");
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.workbook) throw new Error("--workbook is required");
  const workbookPath = path.resolve(args.workbook);
  const outputPath = path.resolve(args.output || workbookPath.replace(/\.xlsx$/i, ".extracted.json"));
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(workbookPath));
  const sheet = workbook.worksheets.getItem("Adjudication");
  if (!sheet) throw new Error("Missing Adjudication sheet");
  const matrix = sheet.getRange("A1:BF71").values;
  const headers = matrix[0].map(text);
  if (JSON.stringify(headers) !== JSON.stringify(EXPECTED_HEADERS)) {
    throw new Error("Adjudication headers differ from the locked v1 template");
  }
  const rows = matrix.slice(1).map((row) => Object.fromEntries(headers.map((header, index) => [header, row[index]])));
  const ids = new Set();
  for (const [index, row] of rows.entries()) {
    const reviewId = text(row.review_id);
    if (!reviewId || reviewId !== text(row.work_id)) throw new Error(`Row ${index + 2}: invalid identity`);
    if (ids.has(reviewId)) throw new Error(`Row ${index + 2}: duplicate review_id ${reviewId}`);
    ids.add(reviewId);
  }
  const formulaErrors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
    options: { useRegex: true, maxResults: 300 },
    summary: "completed workbook formula error scan",
  });
  const payload = {
    schema_version: "af-model-c-human-adjudication-extract-v1",
    workbook_path: workbookPath,
    workbook_sha256: await sha256File(workbookPath),
    extracted_at_utc: new Date().toISOString(),
    record_count: rows.length,
    complete_count: rows.filter((row) => text(row.adjudication_status).toLowerCase() === "complete").length,
    pending_count: rows.filter((row) => text(row.adjudication_status).toLowerCase() !== "complete").length,
    formula_error_scan: formulaErrors.ndjson,
    rows,
  };
  await fs.writeFile(outputPath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  const outputHash = await sha256File(outputPath);
  await fs.writeFile(`${outputPath}.sha256`, `${outputHash}  ${path.basename(outputPath)}\n`, "ascii");
  console.log(`Records: ${rows.length}`);
  console.log(`Complete: ${payload.complete_count}`);
  console.log(`Pending: ${payload.pending_count}`);
  console.log(formulaErrors.ndjson);
  console.log(`Extracted data: ${outputPath}`);
}

main().catch((error) => {
  console.error(error.stack || error.message || String(error));
  process.exitCode = 1;
});
