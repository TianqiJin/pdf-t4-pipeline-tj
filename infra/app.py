#!/usr/bin/env python3
"""CDK app entry point for PDF T4 pipeline."""
import aws_cdk as cdk

from stacks.pipeline_stack import PipelineStack

app = cdk.App()
stack = PipelineStack(
    app,
    "PdfT4PipelineStack",
    openai_param_name=app.node.try_get_context("openai_param_name"),
    openai_secret_arn=app.node.try_get_context("openai_secret_arn"),
    openai_model=app.node.try_get_context("openai_model") or "gpt-4o",
    env=cdk.Environment(),
)
app.synth()
