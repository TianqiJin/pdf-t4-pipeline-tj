"""CDK pipeline stack for PDF T4 pipeline."""
from pathlib import Path

import aws_cdk as cdk
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_notifications as s3n
from aws_cdk import aws_secretsmanager as sm
from aws_cdk import aws_stepfunctions as sfn
from constructs import Construct

try:
    from aws_cdk.aws_lambda_python_alpha import PythonFunction
    HAS_PYTHON_FUNCTION = True
except ImportError:
    HAS_PYTHON_FUNCTION = False


def _asl_template() -> str:
    """Load ASL from STATE_MACHINE_WIRING.md and return as string with placeholders."""
    root = Path(__file__).resolve().parent.parent.parent
    md_path = root / "STATE_MACHINE_WIRING.md"
    content = md_path.read_text()
    start = content.find("```json\n") + 7
    end = content.find("\n```", start)
    return content[start:end].strip()


class PipelineStack(cdk.Stack):
    """Main stack for PDF T4 Step Functions pipeline."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        openai_secret_arn: str | None = None,
        openai_param_name: str | None = None,
        openai_model: str = "gpt-4o",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- S3 Buckets ---
        source_bucket = s3.Bucket(
            self,
            "SourceBucket",
            bucket_name=cdk.PhysicalName.GENERATE_IF_NEEDED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
        )

        split_bucket = s3.Bucket(
            self,
            "SplitBucket",
            bucket_name=cdk.PhysicalName.GENERATE_IF_NEEDED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="ExpireSplits",
                    prefix="splits/",
                    expiration=cdk.Duration.days(1),
                )
            ],
        )

        protected_bucket = s3.Bucket(
            self,
            "ProtectedBucket",
            bucket_name=cdk.PhysicalName.GENERATE_IF_NEEDED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
        )

        results_bucket = s3.Bucket(
            self,
            "ResultsBucket",
            bucket_name=cdk.PhysicalName.GENERATE_IF_NEEDED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
        )

        lambdas_dir = str(Path(__file__).resolve().parent.parent.parent / "lambdas")

        def _make_lambda(
            name: str,
            handler_module: str,
            timeout_sec: int = 60,
            memory_mb: int = 1024,
            env: dict | None = None,
        ) -> lambda_.IFunction:
            merged_env = env or {}
            if HAS_PYTHON_FUNCTION:
                fn = PythonFunction(
                    self,
                    name,
                    entry=lambdas_dir,
                    index=f"{handler_module}/handler.py",
                    handler="handler",
                    runtime=lambda_.Runtime.PYTHON_3_12,
                    timeout=cdk.Duration.seconds(timeout_sec),
                    memory_size=memory_mb,
                    environment=merged_env,
                )
            else:
                fn = lambda_.Function(
                    self,
                    name,
                    runtime=lambda_.Runtime.PYTHON_3_12,
                    handler=f"{handler_module}.handler.handler",
                    code=lambda_.Code.from_asset(lambdas_dir),
                    timeout=cdk.Duration.seconds(timeout_sec),
                    memory_size=memory_mb,
                    environment=merged_env,
                )
            return fn

        # Parse Lambda: OPENAI_API_KEY from Secrets Manager or SSM
        parse_env: dict = {"OPENAI_T4_MODEL": openai_model}
        if openai_secret_arn:
            parse_env["OPENAI_SECRET_ARN"] = openai_secret_arn
        elif openai_param_name:
            parse_env["OPENAI_PARAM_NAME"] = openai_param_name

        starter_lambda = _make_lambda("Starter", "starter", timeout_sec=30)
        split_lambda = _make_lambda("SplitPdf", "split_pdf", timeout_sec=60, memory_mb=1024)
        parse_lambda = _make_lambda(
            "ParseT4", "parse_t4", timeout_sec=120, memory_mb=2048, env=parse_env
        )
        encrypt_lambda = _make_lambda("EncryptPdf", "encrypt_pdf", timeout_sec=60, memory_mb=1024)
        finalize_lambda = _make_lambda("FinalizeJob", "finalize_job")
        cleanup_lambda = _make_lambda("CleanupSplits", "cleanup_splits")

        # Grant parse read from Secrets Manager if used
        if openai_secret_arn:
            secret = sm.Secret.from_secret_complete_arn(self, "OpenAISecret", openai_secret_arn)
            secret.grant_read(parse_lambda)
        elif openai_param_name:
            # SSM: allow all operations (e.g. GetParameter for OpenAI API key)
            parse_lambda.add_to_role_policy(
                iam.PolicyStatement(
                    actions=["ssm:*"],
                    resources=["*"],
                )
            )
            # SecureString params require kms:Decrypt on the key used to encrypt.
            parse_lambda.add_to_role_policy(
                iam.PolicyStatement(
                    actions=["kms:Decrypt"],
                    resources=[f"arn:aws:kms:{self.region}:{self.account}:key/*"],
                    conditions={
                        "StringEquals": {
                            "kms:ViaService": f"ssm.{self.region}.amazonaws.com",
                        }
                    },
                )
            )

        # IAM: split - read source, write split
        source_bucket.grant_read(split_lambda)
        split_bucket.grant_read_write(split_lambda)

        # IAM: parse - read split, write results (internet for OpenAI)
        split_bucket.grant_read(parse_lambda)
        results_bucket.grant_read_write(parse_lambda)

        # IAM: encrypt - read split, write protected + results
        split_bucket.grant_read(encrypt_lambda)
        protected_bucket.grant_write(encrypt_lambda)
        results_bucket.grant_read_write(encrypt_lambda)

        # IAM: finalize - write results
        results_bucket.grant_read_write(finalize_lambda)

        # IAM: cleanup - list + delete split under jobPrefix
        split_bucket.grant_read_write(cleanup_lambda)

        # Step Functions: exact ASL from STATE_MACHINE_WIRING.md
        asl_str = _asl_template()
        asl_str = asl_str.replace("${SplitLambdaArn}", split_lambda.function_arn)
        asl_str = asl_str.replace("${ParseLambdaArn}", parse_lambda.function_arn)
        asl_str = asl_str.replace("${EncryptLambdaArn}", encrypt_lambda.function_arn)
        asl_str = asl_str.replace("${FinalizeLambdaArn}", finalize_lambda.function_arn)
        asl_str = asl_str.replace("${CleanupLambdaArn}", cleanup_lambda.function_arn)

        sfn_role = iam.Role(
            self,
            "StateMachineRole",
            assumed_by=iam.ServicePrincipal("states.amazonaws.com"),
        )
        for fn in [split_lambda, parse_lambda, encrypt_lambda, finalize_lambda, cleanup_lambda]:
            fn.grant_invoke(sfn_role)

        state_machine = sfn.CfnStateMachine(
            self,
            "StateMachine",
            role_arn=sfn_role.role_arn,
            definition_string=asl_str,
        )

        # Starter: S3 incoming/ -> StartExecution
        starter_lambda.add_environment("STATE_MACHINE_ARN", state_machine.attr_arn)
        starter_lambda.add_environment("SPLIT_BUCKET", split_bucket.bucket_name)
        starter_lambda.add_environment("PROTECTED_BUCKET", protected_bucket.bucket_name)
        starter_lambda.add_environment("RESULTS_BUCKET", results_bucket.bucket_name)
        starter_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["states:StartExecution"],
                resources=[state_machine.attr_arn],
            )
        )
        source_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(starter_lambda),
            s3.NotificationKeyFilter(prefix="incoming/"),
        )

        # Outputs
        cdk.CfnOutput(self, "SourceBucketName", value=source_bucket.bucket_name, export_name=f"{self.stack_name}-SourceBucket")
        cdk.CfnOutput(self, "SplitBucketName", value=split_bucket.bucket_name, export_name=f"{self.stack_name}-SplitBucket")
        cdk.CfnOutput(self, "ProtectedBucketName", value=protected_bucket.bucket_name, export_name=f"{self.stack_name}-ProtectedBucket")
        cdk.CfnOutput(self, "ResultsBucketName", value=results_bucket.bucket_name, export_name=f"{self.stack_name}-ResultsBucket")
        cdk.CfnOutput(self, "StateMachineArn", value=state_machine.attr_arn, export_name=f"{self.stack_name}-StateMachineArn")
