"""Unit tests for the Auth CDK stack."""

import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

from infra.auth_stack import AuthStack
from infra.config import EnvironmentConfig


def _synth_template(config: EnvironmentConfig) -> Template:
    app = cdk.App()
    stack = AuthStack(
        app,
        "TestAuth",
        config=config,
        env=cdk.Environment(account=config.aws_account_id, region=config.aws_region),
    )
    return Template.from_stack(stack)


def _dev_config() -> EnvironmentConfig:
    return EnvironmentConfig(
        stage="dev",
        aws_account_id="123456789012",
        aws_region="us-east-1",
        nat_gateways=0,
        tags={"Environment": "dev"},
    )


def _prod_config() -> EnvironmentConfig:
    return EnvironmentConfig(
        stage="prod",
        aws_account_id="123456789012",
        aws_region="us-east-1",
        max_azs=3,
        nat_gateways=2,
        tags={"Environment": "prod"},
    )


class TestAuthStackSecrets:
    """Tests for authentication secrets."""

    def test_two_secrets_created(self) -> None:
        template = _synth_template(_dev_config())
        template.resource_count_is("AWS::SecretsManager::Secret", 2)

    def test_api_keys_secret_name(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::SecretsManager::Secret",
            {"Name": "realtime-agentic-api/dev/api-keys"},
        )

    def test_jwt_secret_name(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::SecretsManager::Secret",
            {"Name": "realtime-agentic-api/dev/jwt-signing-key"},
        )

    def test_dev_secrets_deleted_on_removal(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource(
            "AWS::SecretsManager::Secret",
            {"DeletionPolicy": "Delete"},
        )

    def test_prod_secrets_retained(self) -> None:
        template = _synth_template(_prod_config())
        template.has_resource(
            "AWS::SecretsManager::Secret",
            {
                "DeletionPolicy": "Retain",
                "UpdateReplacePolicy": "Retain",
            },
        )


class TestAuthStackLambdas:
    """Tests for authorizer Lambda functions."""

    def test_two_lambda_functions_created(self) -> None:
        template = _synth_template(_dev_config())
        template.resource_count_is("AWS::Lambda::Function", 2)

    def test_api_key_authorizer_function_name(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "FunctionName": "realtime-agentic-api-dev-api-key-authorizer",
                "Runtime": "python3.11",
                "Handler": "runtime.auth.api_key_authorizer.handler",
            },
        )

    def test_jwt_authorizer_function_name(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "FunctionName": "realtime-agentic-api-dev-jwt-authorizer",
                "Runtime": "python3.11",
                "Handler": "runtime.auth.jwt_authorizer.handler",
            },
        )

    def test_api_key_authorizer_env_vars(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "FunctionName": "realtime-agentic-api-dev-api-key-authorizer",
                "Environment": {
                    "Variables": {
                        "STAGE": "dev",
                        "API_KEYS_SECRET_NAME": Match.any_value(),
                    }
                },
            },
        )

    def test_jwt_authorizer_env_vars(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "FunctionName": "realtime-agentic-api-dev-jwt-authorizer",
                "Environment": {
                    "Variables": {
                        "STAGE": "dev",
                        "JWT_SECRET_NAME": Match.any_value(),
                    }
                },
            },
        )


class TestAuthStackSSMParams:
    """Tests for SSM parameters."""

    def test_ssm_parameters_created(self) -> None:
        template = _synth_template(_dev_config())
        template.resource_count_is("AWS::SSM::Parameter", 4)


class TestAuthStackOutputs:
    """Tests for stack outputs."""

    def test_outputs_present(self) -> None:
        template = _synth_template(_dev_config())
        template.has_output(
            "ApiKeyAuthorizerFnArn",
            {"Description": "API Key authorizer Lambda ARN"},
        )
        template.has_output(
            "JwtAuthorizerFnArn",
            {"Description": "JWT authorizer Lambda ARN"},
        )
        template.has_output(
            "ApiKeysSecretArn",
            {"Description": "API keys secret ARN"},
        )
        template.has_output(
            "JwtSecretArn",
            {"Description": "JWT signing key secret ARN"},
        )
