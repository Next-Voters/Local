"""LocalStack resource provisioning helpers for integration tests."""

import io
import zipfile

import boto3


def create_sqs_queues(endpoint: str) -> dict[str, str]:
    """Create the three SQS queues used by the pipeline.

    Returns:
        Dict with keys 'report_ready', 'pipeline_dlq', 'email_dlq'
        mapped to their queue URLs.
    """
    sqs = boto3.client("sqs", endpoint_url=endpoint, region_name="us-east-1")

    urls = {}
    for name, key in [
        ("report-ready-queue", "report_ready"),
        ("pipeline-dlq", "pipeline_dlq"),
        ("email-dlq", "email_dlq"),
    ]:
        resp = sqs.create_queue(QueueName=name)
        urls[key] = resp["QueueUrl"]

    return urls


def get_queue_arn(endpoint: str, queue_url: str) -> str:
    """Look up the ARN for an SQS queue URL."""
    sqs = boto3.client("sqs", endpoint_url=endpoint, region_name="us-east-1")
    attrs = sqs.get_queue_attributes(
        QueueUrl=queue_url, AttributeNames=["QueueArn"]
    )
    return attrs["Attributes"]["QueueArn"]


def create_ses_identity(endpoint: str, email: str) -> None:
    """Verify an email identity in LocalStack SES."""
    ses = boto3.client("ses", endpoint_url=endpoint, region_name="us-east-1")
    ses.verify_email_identity(EmailAddress=email)


def create_iam_role(endpoint: str, role_name: str = "lambda-role") -> str:
    """Create a minimal IAM role for Lambda execution in LocalStack."""
    iam = boto3.client("iam", endpoint_url=endpoint, region_name="us-east-1")
    trust_policy = (
        '{"Version":"2012-10-17","Statement":[{"Effect":"Allow",'
        '"Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
    )
    try:
        resp = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=trust_policy,
        )
        return resp["Role"]["Arn"]
    except iam.exceptions.EntityAlreadyExistsException:
        resp = iam.get_role(RoleName=role_name)
        return resp["Role"]["Arn"]


def deploy_lambda(
    endpoint: str,
    function_name: str,
    handler_code: str,
    handler_ref: str,
    env_vars: dict[str, str],
    role_arn: str,
) -> str:
    """Deploy a Lambda function from inline Python code.

    Args:
        endpoint: LocalStack endpoint URL.
        function_name: Lambda function name.
        handler_code: Python source code as a string.
        handler_ref: Handler reference (e.g. 'handler.lambda_handler').
        env_vars: Environment variables for the Lambda.
        role_arn: IAM role ARN.

    Returns:
        The Lambda function ARN.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        module_name = handler_ref.split(".")[0]
        zf.writestr(f"{module_name}.py", handler_code)
    buf.seek(0)

    lam = boto3.client("lambda", endpoint_url=endpoint, region_name="us-east-1")

    try:
        lam.delete_function(FunctionName=function_name)
    except lam.exceptions.ResourceNotFoundException:
        pass

    resp = lam.create_function(
        FunctionName=function_name,
        Runtime="python3.11",
        Role=role_arn,
        Handler=handler_ref,
        Code={"ZipFile": buf.read()},
        Environment={"Variables": env_vars},
        Timeout=30,
    )
    return resp["FunctionArn"]
