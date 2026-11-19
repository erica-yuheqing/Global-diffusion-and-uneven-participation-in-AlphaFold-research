#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const EDITABLE_HEADERS = [
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

function parseArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) continue;
    result[token.slice(2)] = argv[index + 1];
    index += 1;
  }
  return result;
}

async function sha256File(filePath) {
  const bytes = await fs.readFile(filePath);
  return crypto.createHash("sha256").update(bytes).digest("hex");
}

async function readJsonl(filePath) {
  const text = await fs.readFile(filePath, "utf8");
  return text
    .split(/\r?\n/)
    .filter((line) => line.trim())
    .map((line, index) => {
      try {
        return JSON.parse(line);
      } catch (error) {
        throw new Error(`${filePath}:${index + 1}: ${error.message}`);
      }
    });
}

function normalizedCell(value) {
  if (value === undefined || value === null || value === "") return null;
  return value;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.workbook || !args["chunks-dir"] || !args.output) {
    throw new Error("Required: --workbook INPUT.xlsx --chunks-dir DIR --output OUTPUT.xlsx");
  }

  const workbookPath = path.resolve(args.workbook);
  const chunksDir = path.resolve(args["chunks-dir"]);
  const outputPath = path.resolve(args.output);
  const inputWorkbookHash = await sha256File(workbookPath);
  const chunkFiles = (await fs.readdir(chunksDir))
    .filter((name) => name.endsWith(".jsonl"))
    .sort()
    .map((name) => path.join(chunksDir, name));
  if (chunkFiles.length === 0) throw new Error(`No JSONL chunks found in ${chunksDir}`);

  const records = (await Promise.all(chunkFiles.map(readJsonl))).flat();
  const byOrder = new Map();
  for (const record of records) {
    const order = Number(record.assignment_order);
    if (!Number.isInteger(order) || order < 1 || order > 150) {
      throw new Error(`Invalid assignment_order: ${record.assignment_order}`);
    }
    if (byOrder.has(order)) throw new Error(`Duplicate assignment_order: ${order}`);
    byOrder.set(order, record);
  }
  if (byOrder.size !== 150) {
    const missing = Array.from({ length: 150 }, (_, index) => index + 1).filter(
      (order) => !byOrder.has(order),
    );
    throw new Error(`Expected 150 records, found ${byOrder.size}; missing ${missing.join(",")}`);
  }

  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(workbookPath));
  const sheet = workbook.worksheets.getItem("Annotations");
  const sourceRows = sheet.getRange("A2:D151").values;
  const matrix = [];
  for (let index = 0; index < sourceRows.length; index += 1) {
    const expectedOrder = index + 1;
    const record = byOrder.get(expectedOrder);
    const [order, reviewerRecordId, reviewId, workId] = sourceRows[index];
    for (const [field, expected, actual] of [
      ["assignment_order", order, record.assignment_order],
      ["reviewer_record_id", reviewerRecordId, record.reviewer_record_id],
      ["review_id", reviewId, record.review_id],
      ["work_id", workId, record.work_id],
    ]) {
      if (String(expected ?? "") !== String(actual ?? "")) {
        throw new Error(
          `Row ${expectedOrder} ${field} mismatch: workbook=${expected} review=${actual}`,
        );
      }
    }
    matrix.push(EDITABLE_HEADERS.map((field) => normalizedCell(record[field])));
  }

  sheet.getRange("I2:AL151").values = matrix;
  const outputDirectory = path.dirname(outputPath);
  await fs.mkdir(outputDirectory, { recursive: true });
  const temporaryPath = path.join(
    outputDirectory,
    `.${path.basename(outputPath)}.${process.pid}.writing.xlsx`,
  );
  const exported = await SpreadsheetFile.exportXlsx(workbook);
  await exported.save(temporaryPath);
  await fs.rename(temporaryPath, outputPath);

  const manifest = {
    schema_version: "af-private-subagent-workbook-fill-v1",
    created_at_utc: new Date().toISOString(),
    input_workbook: path.basename(workbookPath),
    input_workbook_sha256_before_fill: inputWorkbookHash,
    output_workbook: path.basename(outputPath),
    output_workbook_sha256: await sha256File(outputPath),
    record_count: records.length,
    chunk_files: await Promise.all(
      chunkFiles.map(async (filePath) => ({
        file: path.basename(filePath),
        sha256: await sha256File(filePath),
      })),
    ),
  };
  const manifestPath = path.join(chunksDir, "..", "fill_manifest.json");
  await fs.writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  console.log(`Filled records: ${records.length}`);
  console.log(`Output: ${outputPath}`);
  console.log(`Manifest: ${manifestPath}`);
}

main().catch((error) => {
  console.error(error.stack || error.message || String(error));
  process.exitCode = 1;
});
