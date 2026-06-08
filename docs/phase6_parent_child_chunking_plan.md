# Phase 6 - Parent-child Chunking Plan

Tai lieu nay la ke hoach va tracker thuc hien Phase 6. Cac step da hoan thanh
duoc danh dau `[x]` o muc Execution progress. Khong sinh real corpus artifact
cho den khi den step duoc phe duyet rieng.

## 1. Trang thai dau vao

Phase 6 bat dau sau khi Phase 5 Legal Hierarchy Parsing da hoan tat va da duoc
hardening:

- 52/52 van ban co `data/interim/{LAW_ID}/hierarchy.json`.
- Legal hierarchy validator pass 52/52.
- Parser failed = 0.
- RED = 0, ORANGE = 0 trong audit chat luong hierarchy gan nhat.
- Source-tail leakage = 0.
- `AMBIGUOUS_CLAUSE_CANDIDATE = 0`.
- `POINT_LIKE_LINE_OUTSIDE_CLAUSE = 0`.

Input chinh cua Phase 6:

```text
data/interim/{LAW_ID}/hierarchy.json
```

Bao cao Phase 5 dung de doi chieu va audit:

```text
artifacts/reports/parsing/legal_parsing_report.json
```

Phase 6 khong doc lai raw HTML, khong crawl lai, khong clean lai, va khong sua
`normalized.json`, `cleaned.txt`, hay `hierarchy.json` tru khi co blocker da
duoc xac nhan rieng.

## 2. Muc tieu

Xay dung lop parent-child chunking quyet dinh (deterministic) tu
`LegalHierarchyDocument` da co, de tao corpus chunk phuc vu embedding/retrieval
o cac phase sau.

Nguyen tac chinh:

- Don vi con dung de embedding: Clause hoac Point.
- Ngu canh cha dung cho LLM: Article day du.
- Khong cat van ban theo cua so ky tu/token tuy tien.
- Bao toan trace citation den Law / Article / Clause / Point.
- Bao toan offset va `node_id` nguon tu hierarchy.
- Ket qua lap lai phai on dinh bit-for-bit khi input khong doi.

Output chinh du kien:

```text
data/processed/legal_chunks.jsonl
artifacts/reports/chunking/chunking_report.json
```

`legal_chunks.jsonl` la artifact cho toan corpus. Moi dong la mot JSON object
dai dien cho mot legal retrieval chunk.

## 3. Ranh gioi trach nhiem

Phase 6 duoc phep:

- Doc `hierarchy.json`.
- Validate hierarchy truoc khi chunk.
- Chuyen Article / Clause / Point thanh chunk.
- Gan citation, hierarchy path, offsets, hashes, metadata.
- Ghi `data/processed/legal_chunks.jsonl`.
- Ghi `artifacts/reports/chunking/chunking_report.json`.
- Kiem tra determinism, count, uniqueness, va source slicing.

Phase 6 khong duoc:

- Sua legal parser Phase 5 neu khong co blocker rieng.
- Rebuild hierarchy tu normalized text.
- Tach chunk bang arbitrary character/token windows.
- Tao embedding, sparse vector, index Qdrant, BM25, reranker.
- Lam retrieval, RAG, GraphRAG, API, deployment.
- Giai quyet cross-reference graph o muc GraphRAG.
- Dung LLM de cat hoac sua noi dung phap ly.

## 4. Chinh sach chunk

### 4.1 Article la parent context

Moi chunk phai co mot Article cha hop le:

```text
parent_article_node_id -> LegalNode level article
parent_text            -> full Article text
```

`parent_text` la Article span day du tu hierarchy, bao gom Clause va Point con.
Day la ngu canh duoc dua vao LLM o cac phase RAG sau.

### 4.2 Child unit de embedding

Quy tac chon chunk:

1. Neu Clause co Point con:
   - Moi Point tao mot chunk.
   - `text` cua chunk la Point text.
   - `parent_text` la Article text.
2. Neu Clause khong co Point con:
   - Clause tao mot chunk.
   - `text` cua chunk la Clause text.
   - `parent_text` la Article text.
3. Neu Article khong co Clause va khong co Point hop le:
   - Article tao mot article-level chunk.
   - `text` cua chunk la Article text.
   - `parent_text` cung la Article text.

Khong tao synthetic Clause/Point. Khong attach Point truc tiep vao Article neu
hierarchy khong co quan he do.

### 4.3 Empty/repealed Article

Nhung Article bi validator gan canh bao `EMPTY_ARTICLE_NODE` van can duoc xu ly
co chu dich:

- Neu Article co heading hop le nhung noi dung bi bai bo hoac la placeholder,
  tao article-level chunk voi metadata:

```text
is_empty_or_repealed = true
```

- Khong loai bo im lang vi Phase 6 can bao toan citation traceability.
- Bao cao chunking phai dem rieng cac Article nay de Phase 6 audit xem xet.

### 4.4 Source-note va excluded regions

Source-note, footnote tail, appendix, chu ky, va source-law tail da bi loai khoi
legal hierarchy node o Phase 5. Phase 6 khong duoc tao chunk tu cac vung nay.

Root Law text van co the chua source-note trong `root.text`, nhung chunking chi
duoc dua tren Article/Clause/Point nodes hop le, khong dua tren root text thuong.

## 5. De xuat schema chunk

Model du kien: `LegalChunk`.

Truong bat buoc:

```text
schema_version
chunker_version
chunk_id
law_id
law_name
source_url
source_domain
source_type
source_file

level
chunk_kind
source_node_id
parent_article_node_id
parent_chunk_id

article_number
article_title
clause_number
point_label
citation
hierarchy_path

text
parent_text
start_offset
end_offset
article_start_offset
article_end_offset

text_hash
parent_text_hash
metadata
warnings
```

Giai thich:

- `text`: noi dung embedding, la Article/Clause/Point theo quy tac o muc 4.
- `parent_text`: full Article context cho LLM.
- `source_node_id`: `LegalNode.node_id` cua node tao chunk.
- `parent_article_node_id`: `LegalNode.node_id` cua Article cha.
- `parent_chunk_id`: khoa logic cho Article context, khong nhat thiet la mot row
  rieng trong JSONL.
- `hierarchy_path`: duong dan hien thi tu Law -> Part -> Chapter -> Section ->
  Article -> Clause -> Point neu ton tai.

Khong dua raw HTML, full document root text, hay duplicate document-level
metadata lon vao moi chunk neu khong can thiet.

## 6. Dinh danh deterministic

Phase 6 phai dung `node_id` da collision-resolved tu Phase 5 de tranh sinh lai
ID phap ly.

Quy tac de xuat:

```text
chunk_id = "{source_node_id}__chunk"
parent_chunk_id = "{article_node_id}__parent"
```

Vi du:

```text
BLDS_2015__root__article_1__clause_1__point_a__chunk
BLDS_2015__root__article_1__parent
```

Yeu cau:

- `chunk_id` duy nhat tren toan corpus.
- Neu Phase 5 node ID co `__occurrence_2`, chunk ID phai giu suffix do.
- Khong dung ordinal/index runtime de sinh ID neu co the dung hierarchy node ID.
- Lap lai chunking tren cung input phai tao cung ID va cung thu tu dong JSONL.

## 7. Citation va hierarchy path

Citation can dung tieng Viet va bao toan phap ly:

```text
{Law Name}, Điều {article_number}
{Law Name}, Khoản {clause_number}, Điều {article_number}
{Law Name}, Điểm {point_label}, Khoản {clause_number}, Điều {article_number}
```

Neu co VBHN/consolidated title, citation dung ten van ban da co trong metadata
Phase 5. Khong tu y them nam hoac hieu luc neu metadata khong co.

`hierarchy_path` nen bao gom cac muc co thuc:

```text
Law
Part
Chapter
Section
Article
Clause
Point
```

Khong tao muc gia lap khi hierarchy thieu Part/Chapter/Section.

## 8. Validation cho chunk

Can co validator rieng cho chunk output, khong thay the `LegalTreeValidator`.

Kiem tra bat buoc:

- Moi `hierarchy.json` input load duoc thanh `LegalHierarchyDocument`.
- Moi hierarchy pass `LegalTreeValidator`.
- Moi chunk co `chunk_id` duy nhat.
- Moi chunk co `law_id`, `law_name`, `citation`, `source_node_id`.
- `source_node_id` ton tai trong hierarchy.
- `parent_article_node_id` ton tai va level la Article.
- `text` khop voi node source text.
- `parent_text` khop voi Article node text.
- Child span nam trong Article span.
- `text` la substring cua `parent_text` doi voi Clause/Point chunks.
- `start_offset/end_offset` va `article_start_offset/article_end_offset` hop le.
- Khong co chunk nao duoc tao tu Law/Part/Chapter/Section.
- Khong co chunk nao duoc tao tu source-note warning region.
- JSONL parse duoc tung dong.
- So chunk theo law/level khop voi report.

Can bao cao rieng:

- Article khong co Clause/Point.
- Empty/repealed Article chunks.
- Laws co Article count/max mismatch tu Phase 5.
- Laws co node ID collision warning.
- Chunks co `parent_text` qua dai can theo doi cho Phase retrieval.

## 9. Bao cao chunking

Bao cao de xuat:

```text
artifacts/reports/chunking/chunking_report.json
```

Noi dung:

```text
schema_version
chunker_version
started_at
finished_at
duration_seconds
input_dir
output_path
total_laws
successful
failed
total_chunks
chunks_by_level
chunks_by_law
empty_or_repealed_article_chunks
warnings
errors
validation_summary
```

Bao cao phai giup quyet dinh Phase 7/embedding co an toan hay khong.

## 10. Cac file du kien se them khi implement Phase 6

Day chi la du kien cho phase sau, khong duoc tao trong buoc viet tai lieu nay:

```text
src/processing/legal_chunk_models.py
src/processing/legal_chunker.py
src/processing/legal_chunk_validator.py
src/services/chunking_service.py
scripts/chunk_legal_corpus.py

tests/unit/processing/test_legal_chunk_models.py
tests/unit/processing/test_legal_chunker.py
tests/unit/processing/test_legal_chunk_validator.py
tests/unit/services/test_chunking_service.py
tests/unit/services/test_chunk_legal_corpus_cli.py
```

Neu repo da co ten file khac phu hop hon khi bat dau implement, uu tien pattern
thuc te cua repository.

## 11. Trinh tu implement de xuat

### Step 1 - Model va fixture

- Dinh nghia `LegalChunk`, `ChunkingReport`, `ChunkingIssue`,
  `ChunkingSummary`.
- Tao fixture hierarchy nho cho Article-only, Clause-only, Clause/Point,
  missing Part/Chapter/Section, collision IDs, empty/repealed Article.

### Step 2 - Chunk selection

- Load `LegalHierarchyDocument`.
- Tim Article nodes.
- Voi moi Article, chon child chunks theo quy tac:
  Point > Clause > Article fallback.
- Khong tao synthetic nodes.

### Step 3 - Citation va hierarchy path

- Xay citation deterministic.
- Xay `hierarchy_path` bang parent chain co san.
- Bao toan Vietnamese labels.

### Step 4 - Offset va hash

- Gan child offsets va Article offsets.
- Tinh hash deterministic cho `text` va `parent_text`.
- Validate source slicing bang root text trong hierarchy.

### Step 5 - Chunk validator

- Kiem tra uniqueness, parent Article, text/offset, JSONL invariants.
- Tao structured warnings/errors.

### Step 6 - Service va JSONL writer

- Discover `data/interim/{LAW_ID}/hierarchy.json`.
- Chunk tung law doc lap.
- Ghi mot `data/processed/legal_chunks.jsonl`.
- Ghi `artifacts/reports/chunking/chunking_report.json`.
- Isolate loi tung law.

### Step 7 - CLI

- Thin wrapper cho service:

```bash
uv run python scripts/chunk_legal_corpus.py \
  --input-dir data/interim \
  --output data/processed/legal_chunks.jsonl \
  --report artifacts/reports/chunking/chunking_report.json
```

- CLI chi parse arguments, in summary, va tra exit code.

### Step 8 - Priority audit

- Kiem tra cac law uu tien:
  `BLDS_2015`, `BLHS_VBHN`, `LDD_VBHN`, `LTTHC`, `LVL_2025`,
  `LANM_2025`, `LHNGD_VBHN`, `LTATGT_VBHN`.
- Audit citation, parent_text, child text, empty/repealed Article.

### Step 9 - Full corpus run

- Run 52/52 laws.
- Yeu cau failed = 0 truoc khi chuyen sang embedding/indexing.

### Step 10 - Documentation

- Cap nhat README/context/docs sau khi chunk output validated.
- Khong tuyen bo RAG san sang truoc khi retrieval/evaluation phase hoan tat.

## 12. Test plan

Unit tests can co:

- Article-only document tao article-level chunk.
- Article co nhieu Clause tao Clause chunks khi Clause khong co Point.
- Clause co nhieu Point tao Point chunks.
- Article parent context bao gom day du Clause/Point.
- Missing Part/Chapter/Section van chunk dung.
- Collision-resolved node IDs tao chunk IDs on dinh.
- Empty/repealed Article tao chunk co flag rieng.
- Source-note excluded content khong tao chunk.
- `text` va `parent_text` khop exact source node text.
- Offsets hop le va nam trong Article parent.
- Citation dung Article/Clause/Point.
- `hierarchy_path` dung va khong tao synthetic levels.
- JSONL writer giu UTF-8 `ensure_ascii=False`.
- Re-run tren cung input tao output giong nhau.
- Service isolate loi tung law.
- CLI khong ghi vao real paths trong unit tests.

Integration/audit tests can co:

- Process fixture corpus nhieu laws.
- Validate aggregate report counts.
- Confirm `data/processed/legal_chunks.jsonl` parse duoc moi dong.
- Confirm no arbitrary token/window splitting.

## 13. Acceptance criteria

Phase 6 chi nen coi la xong khi:

- 52/52 hierarchy inputs duoc chunk thanh cong.
- `data/processed/legal_chunks.jsonl` duoc tao va validate.
- `artifacts/reports/chunking/chunking_report.json` duoc tao.
- Failed laws = 0.
- Chunk IDs unique toan corpus.
- Moi chunk co citation va Article parent context.
- Moi child text/offset khop hierarchy source node.
- Khong co chunk tu source-note/tail excluded regions.
- Re-run tao ket qua deterministic.
- Cac warning con lai duoc phan loai ro rang la non-blocking hoac blocker.

## 14. Risks va diem can quyet dinh

- Empty/repealed Article: can giu trace citation nhung khong nen gay nhieu
  noise cho retrieval.
- Parent Article qua dai: co the anh huong context packing o phase RAG sau,
  nhung Phase 6 khong duoc cat tuy tien.
- Article count/max mismatch warning tu Phase 5: can dua vao report de Phase 6
  audit, khong ep parser match metadata neu metadata false positive.
- Node ID collision da duoc resolve o Phase 5: Phase 6 phai preserve ID, khong
  sinh lai theo numbering.
- Existing `docs/parent_child_chunking.md` la tai lieu thiet ke cu va co the
  chua dong bo voi trang thai hien tai; tai lieu Phase 6 nay la ke hoach thuc
  hien tiep theo.

## 15. Strict non-goals

Khong implement trong Phase 6:

- Embedding/indexing.
- Qdrant collection.
- Sparse retrieval/BM25.
- Reranking.
- Naive RAG.
- Advanced RAG.
- GraphRAG/cross-reference graph.
- API/backend.
- UI/deployment.
- LLM generation.
- Re-crawling/re-cleaning.
- Sua Phase 5 parser neu khong co blocker ro rang.

## 16. Execution progress

- [x] Step 1 - Model va fixture
- [x] Step 2 - Chunk selection
- [x] Step 3 - Citation va hierarchy path
- [x] Step 4 - Offset va hash
- [x] Step 5 - Chunk validator
- [x] Step 6 - Service va JSONL writer
- [x] Step 7 - CLI
- [x] Step 8 - Priority audit
- [ ] Step 9 - Full corpus run
- [ ] Step 10 - Documentation
