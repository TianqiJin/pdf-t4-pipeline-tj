# STATE_MACHINE_WIRING.md

Source of truth for Step Functions ASL: ItemsPath, Parameters, ResultPath, Choice variables.
Placeholders (e.g. `${SplitLambdaArn}`) remain as-is for deployment substitution.
Must match contracts in CONTRACT.md.

## ASL JSON

```json
{
  "Comment": "PDF T4 Pipeline v1 (Split -> Map(Parse/Encrypt) -> Finalize -> Cleanup)",
  "StartAt": "SplitPdf",
  "States": {
    "SplitPdf": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${SplitLambdaArn}",
        "Payload.$": "$"
      },
      "ResultSelector": { "payload.$": "$.Payload" },
      "ResultPath": "$.splitResult",
      "Next": "MapPages"
    },
    "MapPages": {
      "Type": "Map",
      "ItemsPath": "$.splitResult.payload.pages",
      "MaxConcurrency": 10,
      "Parameters": {
        "jobId.$": "$.splitResult.payload.jobId",
        "buckets.$": "$.splitResult.payload.buckets",
        "prefixes.$": "$.splitResult.payload.prefixes",
        "splitBucket.$": "$.splitResult.payload.split.bucket",
        "page.$": "$$.Map.Item.Value"
      },
      "Iterator": {
        "StartAt": "ParseT4",
        "States": {
          "ParseT4": {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "Parameters": {
              "FunctionName": "${ParseLambdaArn}",
              "Payload.$": "$"
            },
            "ResultSelector": { "payload.$": "$.Payload" },
            "ResultPath": "$.parse",
            "Retry": [
              {
                "ErrorEquals": [
                  "Lambda.ServiceException",
                  "Lambda.AWSLambdaException",
                  "Lambda.SdkClientException",
                  "States.TaskFailed"
                ],
                "IntervalSeconds": 2,
                "BackoffRate": 2.0,
                "MaxAttempts": 3
              }
            ],
            "Next": "ParseChoice"
          },
          "ParseChoice": {
            "Type": "Choice",
            "Choices": [
              {
                "Variable": "$.parse.payload.parseOk",
                "BooleanEquals": true,
                "Next": "EncryptPdf"
              }
            ],
            "Default": "BuildOutcomeParseFailed"
          },
          "EncryptPdf": {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "Parameters": {
              "FunctionName": "${EncryptLambdaArn}",
              "Payload": {
                "jobId.$": "$.jobId",
                "buckets.$": "$.buckets",
                "prefixes.$": "$.prefixes",
                "pageIndex.$": "$.parse.payload.pageIndex",
                "splitKey.$": "$.parse.payload.splitKey",
                "box12Raw.$": "$.parse.payload.box12Raw",
                "box13Raw.$": "$.parse.payload.box13Raw"
              }
            },
            "ResultSelector": { "payload.$": "$.Payload" },
            "ResultPath": "$.encrypt",
            "Retry": [
              {
                "ErrorEquals": [
                  "Lambda.ServiceException",
                  "Lambda.AWSLambdaException",
                  "Lambda.SdkClientException",
                  "States.TaskFailed"
                ],
                "IntervalSeconds": 2,
                "BackoffRate": 2.0,
                "MaxAttempts": 3
              }
            ],
            "Next": "EncryptChoice"
          },
          "EncryptChoice": {
            "Type": "Choice",
            "Choices": [
              {
                "Variable": "$.encrypt.payload.encryptOk",
                "BooleanEquals": true,
                "Next": "BuildOutcomeEncryptSucceeded"
              }
            ],
            "Default": "BuildOutcomeEncryptFailed"
          },
          "BuildOutcomeParseFailed": {
            "Type": "Pass",
            "Parameters": {
              "pageIndex.$": "$.parse.payload.pageIndex",
              "splitKey.$": "$.parse.payload.splitKey",
              "parseOk": false,
              "encryptOk": false,
              "parseResultKey.$": "$.parse.payload.parseResultKey",
              "encryptResultKey": "",
              "protectedKey": "",
              "failureStage": "parse",
              "failureReason.$": "$.parse.payload.failureReason"
            },
            "End": true
          },
          "BuildOutcomeEncryptSucceeded": {
            "Type": "Pass",
            "Parameters": {
              "pageIndex.$": "$.encrypt.payload.pageIndex",
              "splitKey.$": "$.parse.payload.splitKey",
              "parseOk": true,
              "encryptOk": true,
              "parseResultKey.$": "$.parse.payload.parseResultKey",
              "encryptResultKey.$": "$.encrypt.payload.encryptResultKey",
              "protectedKey.$": "$.encrypt.payload.protectedKey",
              "failureStage": null,
              "failureReason": null
            },
            "End": true
          },
          "BuildOutcomeEncryptFailed": {
            "Type": "Pass",
            "Parameters": {
              "pageIndex.$": "$.encrypt.payload.pageIndex",
              "splitKey.$": "$.parse.payload.splitKey",
              "parseOk": true,
              "encryptOk": false,
              "parseResultKey.$": "$.parse.payload.parseResultKey",
              "encryptResultKey.$": "$.encrypt.payload.encryptResultKey",
              "protectedKey": "",
              "failureStage": "encrypt",
              "failureReason.$": "$.encrypt.payload.failureReason"
            },
            "End": true
          }
        }
      },
      "ResultPath": "$.pageOutcomes",
      "Next": "FinalizeJob"
    },
    "FinalizeJob": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${FinalizeLambdaArn}",
        "Payload": {
          "jobId.$": "$.splitResult.payload.jobId",
          "buckets.$": "$.splitResult.payload.buckets",
          "prefixes.$": "$.splitResult.payload.prefixes",
          "pages.$": "$.splitResult.payload.pages",
          "pageOutcomes.$": "$.pageOutcomes"
        }
      },
      "ResultSelector": { "payload.$": "$.Payload" },
      "ResultPath": "$.finalize",
      "Next": "CleanupSplits"
    },
    "CleanupSplits": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${CleanupLambdaArn}",
        "Payload": {
          "jobId.$": "$.splitResult.payload.jobId",
          "split.$": "$.splitResult.payload.split"
        }
      },
      "ResultSelector": { "payload.$": "$.Payload" },
      "ResultPath": "$.cleanup",
      "End": true
    }
  }
}
```
