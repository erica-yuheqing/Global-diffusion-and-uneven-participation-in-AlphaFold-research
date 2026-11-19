# AlphaFold 结构化全文优先管线

这套管线为约 2.9 万篇 AlphaFold 候选研究建立可恢复、可审计的全文语料。它只自动获取明确的开放获取全文或 OpenAlex 已缓存内容，不抓取登录页、不绕过付费墙，也不把普通网页伪装成论文全文。

## 1. 获取顺序

每篇研究依次尝试：

1. Europe PMC 的 JATS XML；
2. OpenAlex 的 GROBID/TEI XML；
3. Unpaywall `best_oa_location` 的 OA PDF；
4. OpenAlex `best_oa_location` 的 OA PDF；
5. OpenAlex 缓存 PDF。

前两项是结构化全文。PDF 在本地通过 GROBID 转为 TEI 后再抽取段落、章节和参考文献链接。OpenAlex 内容接口按文件计费，只有同时传入 `--allow-openalex-content` 和正数 `--max-openalex-content` 才会启用。

## 2. 实现文件

- `03_build_fulltext_manifest.py`：从本地 `derived_tables/works` 建立 SQLite 清单，并补全 Europe PMC、OpenAlex、Unpaywall 元数据；不下载论文正文。
- `04_fetch_fulltext.py`：按上述级联下载全文；自动解开 OpenAlex 的 gzip 包装，再校验 PDF/XML 文件头、限制压缩后与解压后的文件大小，并记录每次尝试和 SHA-256。
- `05_extract_af_contexts.py`：解析 JATS/TEI；将 PDF 交给本地 GROBID；输出全文段落和 AlphaFold 直接提及/种子文献引用上下文。
- `09_enrich_oa_recovery.py`：仅针对 `unavailable` 记录，从 OpenAIRE、CORE、Semantic Scholar 和 Crossref 查找额外 OA 全文候选；只做 DOI/PMID 精确匹配，不下载正文。
- `fulltext_pipeline/common.py`：公共路径、SQLite schema、重试、规范化和哈希函数。
- `fulltext_pipeline/stream_download.py`：正文传输重试、安全 Range 续传，以及每次 HTTP 请求的额度占用和审计记录。
- `tests/test_fulltext_download.py`：仅使用模拟响应和临时目录的离线下载回归测试，不访问论文提供方。
- `../config/alphafold_seed_works.json`：需要在正式运行前冻结的 AlphaFold 种子文献与提及规则。

生成内容位于 `fulltext/`，已加入 `.gitignore`：

```text
fulltext/
├── manifest/fulltext_manifest.sqlite
├── manifest/fulltext_manifest.parquet
├── raw/{epmc_jats,openalex_tei,unpaywall_pdf,openalex_oa_pdf,openalex_pdf}/
├── parsed/grobid/
└── extracted/
```

## 3. 首次准备

以下命令都由你手动执行。本次代码交付没有替你运行任何一条命令。

```bash
cd /historical-workspace/projects/IGN/AlphaFoldResearch

# pyproject.toml 已显式加入 pandas、pyarrow 和 lxml。
# 首次运行会解析依赖并可能更新 uv.lock。
uv sync

export CONTACT_EMAIL='你的机构邮箱'
export UNPAYWALL_EMAIL="$CONTACT_EMAIL"
export OPENALEX_API_KEY='你的 OpenAlex API key'
```

OpenAlex 当前要求 API key；Unpaywall 要求请求中携带邮箱。不要把真实 key 写进脚本、Markdown 或提交记录。

脚本会在 HTTP 错误日志中自动遮蔽 `api_key` 和邮箱；仍不要复制或公开未经检查的完整请求 URL。如果 key 曾出现在终端截图、聊天或公开日志中，应立即撤销并重新生成。

正式构建清单前，先人工检查并冻结种子配置：

```bash
sed -n '1,220p' config/alphafold_seed_works.json
```

如果已经有锁定的 pilot/validation 样本，可提供一个含 `work_id` 列的 CSV，或含 `work_id`/`id` 的 JSONL。样本中的工作会获得最高下载优先级：

```bash
uv run python code/03_build_fulltext_manifest.py init \
  --priority-file /绝对路径/locked_validation_work_ids.csv
```

若暂时没有锁定样本，先按当前候选集初始化：

```bash
uv run python code/03_build_fulltext_manifest.py init
uv run python code/03_build_fulltext_manifest.py summary
```

当前本地审计得到约 `29,127` 个唯一候选。初始化输出还会给出候选 ID 的 SHA-256 指纹。若数量或指纹在正式实验期间变化，应先解释数据版本变化，不要把两版结果混用。

`init` 是 upsert，不会清除已下载状态；重复运行可用于补充标题、摘要和 DOI。新候选集中不存在的旧记录会保留在数据库中，但被标记为非当前语料，不会进入后续获取与统计。若要建立完全独立的新实验，应改用新的 `--db` 和 `--root` 路径，不要直接删除旧清单。

## 4. 20 篇冒烟测试

### 4.1 只补全元数据

`--source all --limit 20` 会让三个提供方检查相同优先序列中的前 20 篇。这里只取元数据，不取正文。

```bash
uv run python code/03_build_fulltext_manifest.py enrich \
  --source all \
  --limit 20 \
  --workers 4

uv run python code/03_build_fulltext_manifest.py summary
uv run python code/03_build_fulltext_manifest.py export --format parquet
```

元数据请求若因网络或限流被标记为 `error`，默认下一次会继续新的 `pending` 记录；需要重试错误项时使用：

```bash
uv run python code/03_build_fulltext_manifest.py enrich \
  --source all \
  --limit 20 \
  --retry-failed \
  --workers 4
```

### 4.2 预览来源，不下载

免费来源预览：

```bash
uv run python code/04_fetch_fulltext.py --limit 20 --dry-run
```

包含 OpenAlex 付费结构化全文的预览：

```bash
uv run python code/04_fetch_fulltext.py \
  --limit 20 \
  --dry-run \
  --allow-openalex-content \
  --max-openalex-content 20
```

从 2026-08-27 的正文重试修订起，`--max-openalex-content 20` 限制的是**本次进程中付费来源的 HTTP 请求尝试数**，不是候选文件数或成功数。初次请求、HTTP 错误重试、正文传输重试、Range 续传和每个重定向请求都在发送前占用同一个线程安全额度；没有额外的底层自动重试。达到上限后，未完成记录保留为可续跑状态。重定向到文件存储的请求也保守计入，但不代表提供方会对每一跳收费；这不是美元账单上限，实际扣款以账户为准。dry-run 的候选数尚未乘入重试和重定向。

### 4.3 下载 20 篇

为了真实测试“结构化全文优先”，启用 OpenAlex TEI，并把付费尝试硬限制为 20：

```bash
uv run python code/04_fetch_fulltext.py \
  --limit 20 \
  --workers 2 \
  --allow-openalex-content \
  --max-openalex-content 20

uv run python code/03_build_fulltext_manifest.py summary
```

若只想测试免费路径：

```bash
uv run python code/04_fetch_fulltext.py --limit 20 --workers 2
```

默认只处理 `pending`，所以再次运行会继续下一批，不会被上一批失败记录卡住。补充元数据、API key 或预算后，使用 `--retry-failed` 重试非成功项；`--force` 会连成功项也重下，可能重复计费，不建议常规使用。

```bash
uv run python code/04_fetch_fulltext.py \
  --limit 20 \
  --retry-failed \
  --workers 2 \
  --allow-openalex-content \
  --max-openalex-content 20
```

OpenAlex 的 GROBID XML 响应是 gzip 文件。脚本会在下载后自动识别 gzip 文件头、受限解压并验证 XML；清单中的最终 `content_bytes` 是解压后落盘文件的大小。若要在放大批次前只复测一篇曾回退到 PDF 的记录，可运行：

```bash
uv run python code/04_fetch_fulltext.py \
  --work-id W3014328819 \
  --force \
  --workers 1 \
  --allow-openalex-content \
  --max-openalex-content 1

uv run python code/03_build_fulltext_manifest.py summary
```

这会允许至多一次付费来源 HTTP 请求。如果接口需要重定向，一次额度可能不足以完成文件获取，应检查结果再决定是否增加额度。只有成功并通过校验的 TEI 才会替换该记录当前的 PDF 获取结果。确认 `fetched_source` 中出现 `openalex_tei` 后，可精确重解析这一篇：

```bash
uv run python code/05_extract_af_contexts.py \
  --work-id W3014328819 \
  --workers 1
```

下载成功后该篇的解析状态会自动重置为 `pending`，因此这里不需要 `--force`。下载命令中的 `--force` 会覆盖该篇已有的成功获取状态，只应与精确的 `--work-id` 一起用于这种复测。

### 4.3.1 正文中断、续传与请求额度

- `--download-attempts 3`（默认 3，可设 1–10）表示**每个候选来源最多 3 轮传输，包含首次请求**。连接错误、可重试 HTTP 状态、正文 `IncompleteRead` 和后续 Range 请求共用这个次数限制；重定向另有 5 跳限制，但每一跳都计入付费 HTTP 额度。
- 中断后保留同目录的 `文件名.part`。满足续传条件时另写 `文件名.part.json`，仅保存来源 URL 的 SHA-256、强 ETag 和期望长度，不保存 API key 或临时签名 URL。下次 CLI 运行可读取这个检查点。
- **只有服务端声明 `Accept-Ranges: bytes`、提供强 ETag、已知总长度且使用 identity 内容编码时才自动续传。** 续传发送 `Range` 和 `If-Range`，并严格检查 `206` 的起点、总长度、ETag 与正文长度；版本或范围不一致时拒绝拼接并重新完整下载。参见 [HTTP Range/If-Range 规范](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.5)。
- 服务端忽略 Range 返回 `200` 时，用这次完整响应替换临时前缀，绝不追加；`416` 不视为文件已完成。缺少安全续传条件、检查点来源变化，或使用 `--no-resume` 时，从头重试。旧版本已删除的临时数据无法恢复，因此这两篇的第一次新请求仍从头开始。
- Requests 会自动解码 HTTP gzip/deflate；此时解码后的字节不能用作服务器的 Range 偏移，故关闭续传。OpenAlex 文件自身的 gzip 包装仍在完整下载后受限解压，兼容原 TEI 工作流。参见 [Requests 流式读取说明](https://docs.python-requests.org/en/stable/user/quickstart/#raw-response-content)。
- 每次 HTTP 请求各记一条 `fetch_attempts`；格式校验不再额外加算一次请求。临时文件只有在完整传输、格式校验和 SHA-256 计算完成后才替换最终文件。失败的下载不会覆盖现有最终文件。不要同时启动选中同一论文的多个下载进程。
- 旧版本留下的 `openalex_paid_attempts` 是候选级计数，新版本新增的是 HTTP 级计数，历史累计不能倒推精确账单。仍按每篇完成时提交清单；强制终止进程可能使当时在途请求的记录尚未提交。**额度只约束当前进程，不跨 CLI 运行共享**，重复执行会产生新的请求和可能的费用。
- `Retry-After` 超过 30 秒时，本来源暂不自动重试，避免长时间阻塞或提前重试；保留错误供稍后处理。磁盘错误、永久 HTTP 错误和格式错误不会进行无意义的同来源网络重试。

当前仅剩两篇 PDF 的手动复测命令（每篇单独最多 6 次 HTTP 请求，两篇合计最多 12 次；不使用 `--force`，已成功项自动跳过）：

```bash
for af_retry_work in W4315776827 W4385796110; do
  caffeinate -i uv run python code/04_fetch_fulltext.py \
    --work-id "$af_retry_work" \
    --retry-failed \
    --openalex-content-only \
    --allow-openalex-content \
    --max-openalex-content 6 \
    --download-attempts 3 \
    --workers 1 \
    2>&1 | tee -a fulltext/logs/openalex_paid_resume_retry.log
done

uv run python code/03_build_fulltext_manifest.py summary
```

若仍失败，先检查新错误以及 `.part` / `.part.json`，不要无限重复付费。可以在上述命令中加 `--dry-run` 仅预览（不访问提供方），但 dry-run 不会探测服务端是否真正支持 Range。

离线测试命令（无需配置 API key）：

```bash
uv run python -B -m unittest discover -s code/tests -p 'test_fulltext_download.py' -v
```

### 4.4 先解析 XML

不启动 GROBID 也可以先解析 JATS/TEI。遇到 PDF 时会标记为 `needs_grobid`，不会退化为丢失引用链接的纯文本解析。

```bash
uv run python code/05_extract_af_contexts.py \
  --limit 20 \
  --workers 2 \
  --combined-jsonl fulltext/extracted/pilot_contexts.jsonl
```

### 4.5 启动 GROBID 后处理 PDF

在另一个终端启动官方 CPU 版 GROBID。`0.9.0-crf` 适合先验证流程；正式解析若有 GPU 和足够资源，可按 GROBID 官方文档改用 full 镜像。

```bash
docker run --rm --init --ulimit core=0 \
  -p 8070:8070 \
  grobid/grobid:0.9.0-crf
```

回到项目终端检查服务并重试之前的 PDF：

```bash
curl --fail http://localhost:8070/api/isalive

export GROBID_URL='http://localhost:8070'

uv run python code/05_extract_af_contexts.py \
  --limit 20 \
  --retry-failed \
  --workers 2 \
  --grobid-url "$GROBID_URL" \
  --combined-jsonl fulltext/extracted/pilot_contexts.jsonl

uv run python code/03_build_fulltext_manifest.py summary
```

抽取结果中的 `paragraphs` 保存正文段落、列表项、图注和无段落包装的表格行，并用 `block_type` 区分；`evidence_contexts` 是命中文本块及其前后块；`matched_seed_references` 保留命中的 AlphaFold 种子参考文献。模型输入可优先使用证据窗口，只有判定困难时才传入完整 `paragraphs`。

## 5. 500 篇 pilot

应优先使用已锁定、分层覆盖的 500 篇工作 ID，而不是简单取前 500 篇。将它们写入 `locked_validation_work_ids.csv` 后重新执行 `init --priority-file ...` 即可把这些记录置顶。

```bash
uv run python code/03_build_fulltext_manifest.py init \
  --priority-file /绝对路径/locked_validation_work_ids.csv

uv run python code/03_build_fulltext_manifest.py enrich \
  --source all \
  --limit 500 \
  --priority-max 0 \
  --workers 6

uv run python code/04_fetch_fulltext.py \
  --limit 500 \
  --priority-max 0 \
  --workers 4 \
  --allow-openalex-content \
  --max-openalex-content 500

uv run python code/05_extract_af_contexts.py \
  --limit 500 \
  --priority-max 0 \
  --workers 2 \
  --grobid-url "$GROBID_URL" \
  --combined-jsonl fulltext/extracted/pilot_contexts.jsonl

uv run python code/03_build_fulltext_manifest.py summary
uv run python code/03_build_fulltext_manifest.py export --format parquet
```

`--priority-max 0` 将这三步限制在锁定样本内；500 是其中待处理记录的上限。有些记录可能没有合法全文 URL。OpenAlex 付费上限同样是尝试次数，因此实际成功全文数和付费次数都应从清单中核对。

## 6. 全量运行

只有在 20 篇冒烟测试和 500 篇 pilot 的文件质量、种子引用匹配率、GROBID 解析率与费用均可接受后，再运行全量。

先补全所有元数据：

```bash
uv run python code/03_build_fulltext_manifest.py enrich \
  --source all \
  --workers 8

uv run python code/03_build_fulltext_manifest.py summary
uv run python code/03_build_fulltext_manifest.py export --format parquet
```

先用 `--dry-run --all` 检查来源。真正下载时，必须把下面的 `PAID_FILE_CAP` 改成你已批准的付费尝试数；不要照搬一个未经确认的大额上限。

```bash
export PAID_FILE_CAP=500

uv run python code/04_fetch_fulltext.py \
  --all \
  --dry-run \
  --allow-openalex-content \
  --max-openalex-content "$PAID_FILE_CAP"

uv run python code/04_fetch_fulltext.py \
  --all \
  --workers 6 \
  --allow-openalex-content \
  --max-openalex-content "$PAID_FILE_CAP"
```

`PAID_FILE_CAP=500` 只是保守示例，约对应最高 5 美元的 OpenAlex 内容请求。若剩余 `deferred_paid_source` 需要继续获取，可在下一次命令中提高已批准的单次上限并加 `--retry-failed`。每次命令的上限独立计数，因此累计预算需要由清单和 OpenAlex 账户共同核对。

全文下载完成后解析全部尚未解析的记录：

```bash
uv run python code/05_extract_af_contexts.py \
  --all \
  --workers 2 \
  --grobid-url "$GROBID_URL" \
  --combined-jsonl fulltext/extracted/all_contexts.jsonl

uv run python code/03_build_fulltext_manifest.py summary
uv run python code/03_build_fulltext_manifest.py export --format parquet
```

## 7. 无来源记录的 OA 补漏层

这一层用于原始 Europe PMC、Unpaywall、OpenAlex 元数据中没有可用来源、因而被标记为 `unavailable` 的记录。它不调用 Sci-Hub、不绕过登录或付费墙，也不把标题相似的论文自动当作同一篇。候选必须通过 DOI 或 PMID 精确匹配，并保留提供方、许可证/开放状态证据、响应哈希和直接 URL，供后续审计。

查询顺序是 OpenAIRE、CORE、Semantic Scholar、Crossref：

- OpenAIRE：接受明确标为 Open Access/Open Source 且看起来是直接 PDF/XML 的实例 URL；
- CORE：保留 DOI 精确匹配结果的 `downloadUrl`，并添加 `sourceFulltextUrls` 中的原始仓储 PDF/XML 直链作为备用来源；空列表、只有原始仓储链接的结果也能处理。仓储记录页和 arXiv abstract 页不会被当成 PDF；
- Semantic Scholar：只接受 `isOpenAccess=true` 的 `openAccessPdf`；其中 DOI/Handle/机构记录页保留为 `landing_only`。PMC 页面只能提供 PMCID，不能证明可下载 XML：还需匹配该 PMCID 的 Europe PMC OA + 全文可用标记，或通过单独的元数据核验；
- Crossref：只接受同时存在明确开放许可证和 PDF/XML `link` 的记录；普通 publisher/TDM link 不会仅因存在就自动下载。`api.elsevier.com` 的 Article API 地址只有配置 Elsevier API key 后才会进入下载级联。

环境变量：

```bash
export CONTACT_EMAIL='你的机构邮箱'
export CORE_API_KEY='你的 CORE API key'
export SEMANTIC_SCHOLAR_API_KEY='你的 Semantic Scholar API key'  # 可选
export ELSEVIER_API_KEY='你的 Elsevier API key'                    # 可选
```

### 7.1 锁定已经检查过的原始 200 篇 Pilot

随机种子只对不变的候选池有确定性。部分论文下载成功后，`fetch_status='unavailable'` 的候选池会变化，**仅重复原来的 `--sample-seed` 不能保证仍是同一批论文**。补源重试和下载均应改用固定 ID 清单。

目前四家提供方的历史检查表恰好具有相同的 200 个 ID。用下面的本地命令从检查表恢复并冻结它们；不查询提供方、不更改 manifest，只创建 JSON lock。若四家的 ID 集合不同、数量不符，或目标文件已有不同内容，脚本会拒绝操作：

```bash
uv run python code/09_enrich_oa_recovery.py \
  --freeze-checked-pilot fulltext/pilot/oa_recovery_200.lock.json \
  --expected-cohort-size 200
```

清单包含 ID、数量、SHA-256 和来源说明。后续传入 `--cohort-file` 时，metadata 查询不会因下载状态变化而换样；下载器仍跳过已成功下载的论文。`--all` 与 `--cohort-file` 同用只表示处理锁定样本内的全部合格记录，不是全部 29,127 篇。不要手动修改 lock；`--sample-seed --retry-failed` 的组合现在会报错，要求使用固定清单。

### 7.2 本地修复旧候选，不访问网络

先预演，再保存本地候选更新。预演只修改内存副本；正式修复不改动论文文件、作品下载状态或既有请求历史。

```bash
uv run python code/09_enrich_oa_recovery.py \
  --repair-existing \
  --cohort-file fulltext/pilot/oa_recovery_200.lock.json \
  --dry-run

uv run python code/09_enrich_oa_recovery.py \
  --repair-existing \
  --cohort-file fulltext/pilot/oa_recovery_200.lock.json

uv run python code/03_build_fulltext_manifest.py summary
```

修复包括：

- 从历史请求中识别 403/404/410 与不合格文件，分别隔离为 `http_403`、`http_404`、`http_410`、`invalid_payload`。这些是某个 URL 的状态，不代表论文本身无法获得，更不代表没有使用 AlphaFold。
- PMC 已知非 OA 标为 `pmc_not_oa`；证据不够标为 `needs_pmc_check`，不直接请求 `fullTextXML`。
- 从已有 CORE `landing_url`/证据中的原始仓储地址补出直链，保留缓存 URL 和失败历史。
- 已下载候选保持 `downloaded`，重新查元数据不会将其或隔离 URL 重置为 `available`；过时的普通候选保留为 `superseded`，不会删除审计记录。

`--classify-existing` 仍可使用，但现在是整个本地修复的别名。计数按候选 URL，而不是按论文去重；修复各子步骤的计数可能重叠，也不等于最终状态分布。

2026-08-27 对当前 manifest 的内存副本预演结果：补出 5 个 CORE 原始直链，其中 4 篇已下载，仅 **W4290673782** 是新增可尝试下载的论文；7 个 PMC XML 候选中 6 个非 OA、1 个需要元数据核验。正式数据库仍为 `fetch_success=19,156`，修复不会自行增加该数字。

### 7.3 先尝试新直链，下载仍限定在 Pilot 内

```bash
uv run python code/04_fetch_fulltext.py \
  --cohort-file fulltext/pilot/oa_recovery_200.lock.json \
  --limit 200 \
  --retry-failed \
  --oa-recovery-only \
  --dry-run
```

在上述清单状态下，未配置 Elsevier key 时应看到 `Eligible rows: 1`，来源是 `core_oa`。核对后手动运行：

```bash
caffeinate -i uv run python code/04_fetch_fulltext.py \
  --cohort-file fulltext/pilot/oa_recovery_200.lock.json \
  --limit 200 \
  --retry-failed \
  --oa-recovery-only \
  --download-attempts 3 \
  --workers 2 \
  2>&1 | tee -a fulltext/logs/oa_recovery_fetch_pilot_v2.log

uv run python code/03_build_fulltext_manifest.py summary
```

本命令不请求 OpenAlex 付费内容。未设置 `ELSEVIER_API_KEY` 时仍跳过 Elsevier Article API。通常不要添加 `--force` 或 `--retry-blocked-oa`：普通 `--retry-failed` 不会重新访问隔离的失效 URL；后者仅在明确想复查这些 URL 时使用，且不能绕过 PMC OA 检查。

### 7.4 只补查失败的元数据，再核验待定 PMC

先 dry-run 确认原始 Pilot 内仍是 CORE 18 条、Semantic Scholar 69 条 provider error（若已重试过，数量会减少）。下载成功不会改变这批 metadata 重试的 ID 范围。

```bash
uv run python code/09_enrich_oa_recovery.py \
  --source core \
  --cohort-file fulltext/pilot/oa_recovery_200.lock.json \
  --all \
  --retry-failed \
  --dry-run

uv run python code/09_enrich_oa_recovery.py \
  --source semantic_scholar \
  --cohort-file fulltext/pilot/oa_recovery_200.lock.json \
  --all \
  --retry-failed \
  --dry-run
```

然后分别运行，不要并发启动多个 metadata 进程：

```bash
caffeinate -i uv run python code/09_enrich_oa_recovery.py \
  --source core \
  --cohort-file fulltext/pilot/oa_recovery_200.lock.json \
  --all \
  --retry-failed \
  --workers 1 \
  --request-interval 3 \
  2>&1 | tee -a fulltext/logs/oa_recovery_core_retry.log

caffeinate -i uv run python code/09_enrich_oa_recovery.py \
  --source semantic_scholar \
  --cohort-file fulltext/pilot/oa_recovery_200.lock.json \
  --all \
  --retry-failed \
  --workers 1 \
  --request-interval 5 \
  2>&1 | tee -a fulltext/logs/oa_recovery_s2_retry.log
```

限速由同一进程内共享的 provider pacer 实施，重试也受最小间隔控制。默认 CORE 2.1 秒、Semantic Scholar 3.1 秒，以上命令采用更保守的 3/5 秒；它们是本项目的请求间隔，不是保证服务端允许的配额。若遇到 429，本次运行暂停该提供方的新请求；已在途请求可能完成，其余 `deferred_rate_limit` 不覆盖原有检查记录。之后等待配额恢复再手动重试，不要立即循环运行。普通网络/5xx 错误最多尝试 3 次。

CORE 单独真实查询需要配置 key；`--source all` 未配置 CORE key 时会明确跳过 CORE，其他提供方继续。Semantic Scholar key 可选；持续遇到限流时，不要通过加并发强行重试。

新找到的 PMC 页面若没有充分 OA 证据，会进入 `needs_pmc_check`。下一步只查询 Europe PMC metadata，核对 PMCID + DOI（无 DOI 时核对 PMID）及 OA/全文标记，不下载论文正文：

```bash
uv run python code/09_enrich_oa_recovery.py \
  --verify-pmc \
  --cohort-file fulltext/pilot/oa_recovery_200.lock.json \
  --all \
  --dry-run

uv run python code/09_enrich_oa_recovery.py \
  --verify-pmc \
  --cohort-file fulltext/pilot/oa_recovery_200.lock.json \
  --all

uv run python code/04_fetch_fulltext.py \
  --cohort-file fulltext/pilot/oa_recovery_200.lock.json \
  --all \
  --retry-failed \
  --oa-recovery-only \
  --dry-run
```

通过 PMC 核验才标为 `available`；非 OA、身份不符、未在全文库可用分别保留为 `pmc_not_oa`、`pmc_id_mismatch`、`pmc_unavailable`。请求错误保留为 `needs_pmc_check`，可再次核验；默认不重查已明确否定的候选，明确需要更新这些结论时才用 `--verify-pmc --force`。

最后一个 dry-run 确认后才去掉 `--dry-run` 下载。补源 metadata 的 `found` 和候选数量都不等于实际下载成功数；当前 Pilot 初次净新增为 12/200（6%）。应以固定 200 篇的新增全文、失败原因和人工质量检查评估是否值得扩展，不要直接将 36 条有来源记录的成功率当作全部无来源论文的成功率。

### 7.5 离线回归测试

以下测试只使用临时 SQLite、合成响应和内存副本，禁止真实 socket 连接，不消耗 API 额度：

```bash
uv run python -B -m unittest discover -s code/tests -p 'test_*.py' -q
```

开发验证使用项目已有 `.venv/bin/python -B`，没有同步依赖或运行真实补源/下载任务。

## 8. 运行后检查点

每个阶段至少检查：

- `works` 是否仍等于冻结的候选数；
- `epmc_oa_xml`、`openalex_tei` 和各 PDF 来源的覆盖率；
- `fetch_success` 与 `parse_success`，以及各状态的失败类型；
- 下载文件是否有异常小文件、HTML 冒充 PDF/XML 或重复 SHA-256；
- `evidence_context_count=0` 的比例，特别是 citation-only 记录；
- 随机阅读 JATS、OpenAlex TEI、各 PDF 来源的抽取结果；
- 对 PDF→GROBID 结果，核验参考文献条目与正文引用链接是否仍然对应；
- OpenAlex 内容请求次数是否低于人工批准上限。

自动获取不到的记录应保留为 `unavailable`、`failed` 或 `deferred_paid_source`，不要用摘要推断成“全文未使用 AlphaFold”。这些记录后续进入机构订阅/TDM 获取，或者在分析中明确标记为 `U`。

若某个 OA PDF URL 过期或解析服务曾暂时失败，先用元数据脚本的 `--force` 刷新对应提供方，再对下载/解析脚本使用 `--retry-failed`。GROBID 的 `--workers 2` 是保守起点；只有观察到本机内存和 GROBID 队列稳定后再逐步提高。

OpenAlex 缓存文件仍保留原始论文版权，OpenAlex 不额外授予重分发权。请仅在机构授权、开放许可或适用的文本与数据挖掘规则下使用，并只发布允许公开的派生数据和证据片段。

### 8.1 全文质量复核清单（本地只读导出）

`10_build_fulltext_qa.py` 只读取 manifest 与现有解析 JSON，导出新的 QA 快照，不访问提供方、不运行 GROBID/OCR/LLM，也不修改数据库、原论文或旧 Pilot 输入。

选择范围：当前语料中已下载成功，且解析失败，或解析成功但清单中 AF 证据片段数为零。它不是对所有已解析论文的完整质量审计。

2026-08-28 首份清单位于 `fulltext/qa/20260828_review/`：

- 总计 448 个不重复 work_id：50 篇解析失败 + 398 篇无片段。
- P0：13 篇提取文本不足 1,000 个字符，优先核对是否为研究正文、撤回/重复发布说明或漏提取。
- P1：50 篇解析错误 + 11 篇旧版 `af-fulltext-context-v1` JSON。旧格式不是文件损坏，但当前模型输入脚本要求 v2；应优先复用已有 TEI 升级。
- P2：其余 374 篇无 AF 片段记录。没有片段不能自动解释为没有采用 AlphaFold。
- 74 篇 P0/P1 是优先处理项；11 篇旧格式属于原 398 篇无片段记录，不额外增加总数。

重新预览当前情况（不生成文件）：

```bash
uv run python code/10_build_fulltext_qa.py \
  --immutable \
  --observations config/fulltext_qa_observations_20260828.json \
  --dry-run
```

`--immutable` 仅适用于下载/解析/补源任务均已停止、数据库没有 WAL/journal 的情况。脚本会检查旁文件并检测检查期间的文件变化；有其他任务写入时不要使用该参数。常规读连接可以省略 `--immutable`。

需要新的快照时使用以下命令，默认按 UTC 时间创建新目录；不会覆盖已填写的旧复核资料：

```bash
uv run python code/10_build_fulltext_qa.py \
  --immutable \
  --observations config/fulltext_qa_observations_20260828.json
```

输出为 `fulltext_qa_review.jsonl`、带选择条件/阈值/哈希的 `fulltext_qa_review.meta.json` 和 `README.md`。字符数是非空段落去除首尾空白后的 Unicode 字符数之和，不是 token 数、英文词数或 PDF 字节数。原字段为空时保留未知，不能把解析失败的上下文数当成零证据。

配套 Excel 包含 Overview、Review、Snapshot、Guide 四张表。只在 Review 的 C:G 蓝色区域填写复核状态、质量结论、复核人、日期和备注；保留 work_id。原始快照与此前抽查观察分开存放，不会预先把任何记录标为已完成。

人工复核结论仅用于文件/解析质量；不得直接等同 AF 采用等级或自动纳入/排除。Excel 与 JSONL/SQLite 不自动同步。先完成质量复核及必要的版本升级，再决定如何更新模型输入准入规则并生成新版 Pilot 包；本步骤不覆盖原模型输入、评分键或抽样 ID。

### 8.2 Pilot 2+1 机器共识冻结

Model C 推荐范围完成 69/69 条本地有效输出后，使用冻结的 A/B 规范输出、C 输出、三个 C run artifacts、原始 Pilot 和 v5 输入生成机器共识：

```bash
uv run python code/21_finalize_pilot_ensemble.py
```

输入锁为 `fulltext/pilot/calibration/pilot_150_ensemble_v4_3.lock.json`。程序会先检查全部源文件 SHA-256、C 的 69 个唯一 ID、本地 Schema/语义验证、OpenRouter 传输签名、run artifact 内部完整性和历史错误是否均已有有效输出；任何检查失败都会停止，不会生成部分合并结果。

投票分别以完整核心字段组和规范化 `observed_actions` 集合为单位，不逐字段拼接。进入 C 的记录必须形成精确 2/3 多数；代表响应必须来自核心与动作两个获胜联盟的共同模型。无多数、U/RU、E0/E1、摘要级实际使用、forced-U 或任何模型声明人工复核的记录均进入强制人工队列。

输出目录为 `fulltext/pilot/ensemble_v4_3/`：

- `pilot_150_machine_consensus_v4_3.jsonl`：包含三模型投票、响应哈希、运行来源、人工路由和抽样信息；
- `pilot_150_machine_consensus_v4_3.csv`：扁平化检查表；
- `pilot_150_operational_human_queue_v4_3.csv`：强制人工记录加确定性分层审计样本；
- `pilot_150_double_annotation_queue_v4_3.csv`：暴露机器结果的协调/裁决表；不得作为独立人工标注输入；
- `pilot_150_machine_consensus_report_v4_3.json`：一致性、标签分布、人工原因、artifact 和实际上游路由汇总。

所有输出均带 `.sha256`。机器共识不是人工参考准确率；没有独立双人标签前不得由这些文件计算或声称 precision、recall、sensitivity、specificity 或最终 confusion matrix。

### 8.3 Pilot 双人独立盲标

真正的独立标注输入必须与机器共识隔离。先生成 150 条盲化 packet 和两个确定性随机顺序：

```bash
uv run python code/22_prepare_blinded_human_annotation.py
```

工作簿由 `code/22_build_blinded_human_annotation_workbooks.mjs` 生成，最终模板位于：

- `outputs/01a0091f-5dc1-7010-b3cd-76ccabfd945c/human_annotation_v4_3/pilot_150_annotator_A_blinded_v4_3.xlsx`
- `outputs/01a0091f-5dc1-7010-b3cd-76ccabfd945c/human_annotation_v4_3/pilot_150_annotator_B_blinded_v4_3.xlsx`

模板排除 A/B/C 输出、旧检索标签、sampling 字段、`evidence_tier`、`model_eligible` 和 `forced_decision`。两份表包含相同 150 个 ID，但顺序不同。空白模板不得直接覆盖；应复制为 completed 工作副本后分发，且两位标注者在结果锁定前不得互看。

填写期间可只做身份和进度检查：

```bash
uv run python code/23_validate_pilot_human_annotations.py \
  --annotator-a fulltext/pilot/human_annotation_v4_3/completed/pilot_150_annotator_A_completed_v4_3.xlsx \
  --annotator-b fulltext/pilot/human_annotation_v4_3/completed/pilot_150_annotator_B_completed_v4_3.xlsx \
  --allow-incomplete \
  --dry-run
```

两边均完成后，去掉 `--allow-incomplete --dry-run`。程序会验证 ID/顺序、受控值、跨字段一致性、动作—证据映射和逐字引文，并在 `fulltext/pilot/human_annotation_v4_3/results/` 生成验收报告与人工分歧裁决 CSV。只有两位标注者均完成且所有验证通过后，才可向裁决者解盲机器共识；之后才能评估模型性能或决定全量协议。

#### v6 最终盲标工作簿

v6 使用 `af-review-v4`、`af-context-window-v2` 和刷新后的摘要/正文证据。重新生成盲化 packet 与两个独立随机顺序：

```bash
uv run python code/22_prepare_blinded_human_annotation.py \
  --input fulltext/pilot/model_inputs_v6/pilot_model_inputs.jsonl \
  --output-dir fulltext/pilot/human_annotation_v6 \
  --version-tag v6 \
  --protocol-version af-review-v4 \
  --codebook-file config/af_review_prompt_v4.txt \
  --schema-file config/af_review_output_schema_v2.json
```

工作簿生成器支持 `--version-tag`、动态 manifest 路径和防覆盖检查。v6 空白模板位于：

- `outputs/01a0091f-5dc1-7010-b3cd-76ccabfd945c/human_annotation_v6/pilot_150_annotator_A_blinded_v6.xlsx`
- `outputs/01a0091f-5dc1-7010-b3cd-76ccabfd945c/human_annotation_v6/pilot_150_annotator_B_blinded_v6.xlsx`

带 `copy` 且由 GPT/subagent 填写的历史工作簿只作为机器比较结果，不得计作人工双标或人工金标准。应将上述 v6 空白模板分别交给两名人工标注者，且在双方锁定前相互隔离，也不展示机器共识。

填写期间验证命令：

```bash
uv run python code/23_validate_pilot_human_annotations.py \
  --annotator-a fulltext/pilot/human_annotation_v6/completed/pilot_150_annotator_A_completed_v6.xlsx \
  --annotator-b fulltext/pilot/human_annotation_v6/completed/pilot_150_annotator_B_completed_v6.xlsx \
  --packet-file fulltext/pilot/human_annotation_v6/pilot_150_human_packets_blinded_v6.jsonl \
  --assignment-a fulltext/pilot/human_annotation_v6/pilot_150_annotator_a_assignment_v6.json \
  --assignment-b fulltext/pilot/human_annotation_v6/pilot_150_annotator_b_assignment_v6.json \
  --output-dir fulltext/pilot/human_annotation_v6/results \
  --result-tag v6 \
  --allow-incomplete \
  --dry-run
```

两边全部完成后移除 `--allow-incomplete --dry-run`。验证器会输出 v6 验收报告和人工分歧裁决清单；完成第三人裁决后，才能把人工金标准与 `ensemble_v6` 比较。

## 9. 官方接口说明

- [OpenAlex full-text PDFs/TEI XML](https://developers.openalex.org/download/full-text-pdfs)
- [OpenAlex filtering](https://developers.openalex.org/guides/filtering)
- [Europe PMC REST fullTextXML](https://dev.europepmc.org/RestfulWebService)
- [Unpaywall REST API](https://unpaywall.org/api)
- [GROBID quick start](https://grobid.readthedocs.io/en/latest/getting_started/)
- [OpenAIRE Graph API v3](https://graph.openaire.eu/docs/apis/graph-api/)
- [CORE API](https://core.ac.uk/services/api)
- [Semantic Scholar Academic Graph API](https://api.semanticscholar.org/api-docs/graph)
- [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)
- [Elsevier Article Retrieval / text-mining API](https://dev.elsevier.com/tecdoc_text_mining.html)
