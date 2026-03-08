# CONTRACT.md

API contracts, Lambda input/output schemas, and state machine payload shapes.

## Step Function execution input

```json
{
  "jobId": "optional-uuid",
  "source": { "bucket": "SOURCE_BUCKET", "key": "incoming/my.pdf" },
  "buckets": { "split": "SPLIT_BUCKET", "protected": "PROTECTED_BUCKET", "results": "RESULTS_BUCKET" },
  "prefixes": { "split": "splits/", "protected": "protected/", "results": "results/" }
}
```

## split_pdf output

```json
{
  "jobId": "uuid",
  "source": { "bucket": "SOURCE_BUCKET", "key": "incoming/my.pdf" },
  "buckets": { "split": "SPLIT_BUCKET", "protected": "PROTECTED_BUCKET", "results": "RESULTS_BUCKET" },
  "prefixes": { "split": "splits/", "protected": "protected/", "results": "results/" },
  "split": { "bucket": "SPLIT_BUCKET", "jobPrefix": "splits/uuid/" },
  "pages": [ { "pageIndex": 1, "splitKey": "splits/uuid/page-0001.pdf" } ],
  "pageCount": 50
}
```

## parse_t4 input (per page)

```json
{
  "jobId": "uuid",
  "buckets": { "split": "SPLIT_BUCKET", "protected": "PROTECTED_BUCKET", "results": "RESULTS_BUCKET" },
  "prefixes": { "split": "splits/", "protected": "protected/", "results": "results/" },
  "splitBucket": "SPLIT_BUCKET",
  "page": { "pageIndex": 1, "splitKey": "splits/uuid/page-0001.pdf" }
}
```

## parse_t4 output (success)

```json
{
  "pageIndex": 1,
  "splitKey": "splits/uuid/page-0001.pdf",
  "parseOk": true,
  "box12Raw": "123456RT",
  "box13Raw": "",
  "parseResultKey": "results/uuid/page-0001-parse.json",
  "failureReason": null
}
```

## parse_t4 output (failure)

```json
{
  "pageIndex": 1,
  "splitKey": "splits/uuid/page-0001.pdf",
  "parseOk": false,
  "box12Raw": "",
  "box13Raw": "",
  "parseResultKey": "results/uuid/page-0001-parse.json",
  "failureReason": "Not a T4 slip"
}
```

## encrypt_pdf input

```json
{
  "jobId": "uuid",
  "buckets": { "split": "SPLIT_BUCKET", "protected": "PROTECTED_BUCKET", "results": "RESULTS_BUCKET" },
  "prefixes": { "split": "splits/", "protected": "protected/", "results": "results/" },
  "pageIndex": 1,
  "splitKey": "splits/uuid/page-0001.pdf",
  "box12Raw": "123456RT",
  "box13Raw": ""
}
```

## encrypt_pdf output (success)

```json
{
  "pageIndex": 1,
  "encryptOk": true,
  "protectedKey": "protected/uuid/page-0001.pdf",
  "encryptResultKey": "results/uuid/page-0001-encrypt.json",
  "failureReason": null
}
```

## encrypt_pdf output (failure)

```json
{
  "pageIndex": 1,
  "encryptOk": false,
  "protectedKey": "",
  "encryptResultKey": "results/uuid/page-0001-encrypt.json",
  "failureReason": "Box12 and Box13 invalid: both empty; need all digits or digits before RT"
}
```

## finalize_job input

```json
{
  "jobId": "uuid",
  "buckets": { "split": "...", "protected": "...", "results": "..." },
  "prefixes": { "split": "...", "protected": "...", "results": "..." },
  "pages": [ { "pageIndex": 1, "splitKey": "..." } ],
  "pageOutcomes": [ { "pageIndex": 1, "splitKey": "...", "parseOk": true, "encryptOk": true, "parseResultKey": "results/uuid/page-0001-parse.json", "encryptResultKey": "results/uuid/page-0001-encrypt.json", "protectedKey": "protected/uuid/page-0001.pdf", "failureStage": null, "failureReason": null } ]
}
```

## finalize_job output

```json
{
  "jobId": "uuid",
  "summaryKey": "results/uuid/summary.json",
  "succeededCount": 47,
  "failedCount": 3
}
```

## cleanup_splits input

```json
{
  "jobId": "uuid",
  "split": { "bucket": "SPLIT_BUCKET", "jobPrefix": "splits/uuid/" }
}
```

## cleanup_splits output

```json
{
  "jobId": "uuid",
  "cleaned": true,
  "deletedCount": 50
}
```

---

## Result file formats

### parse_t4

parse_t4 must write full result JSON to `buckets.results` at `parseResultKey`:

- **Failure file:** `{ "isAbleToGetContent": false, "Reason": "..." }`
- **Success file:** `{ "isAbleToGetContent": true, "slipType": "T4"|"T4A", "year": int, "employerName": str, "employeeName": str, "employeeAddress": str, "boxes": {...}, "codes": {...} }`

Supports both Canada T4 (employment) and T4A (pension/annuity/other income) slips. Encryption uses Box 12/012 first (SIN), then Box 13/013 if Box 12 is empty. Both accept: all digits, or digits before RT.

### encrypt_pdf

encrypt_pdf must write a result JSON to `buckets.results` at `encryptResultKey`.

### finalize_job

finalize_job must write summary JSON to `buckets.results` at `summaryKey` listing `succeededPages` + `failedPages` with `pageIndex`/`stage`/`reason`.

---

## Security

**Do not log Box12 or Box13.** These values must never be written to logs.
