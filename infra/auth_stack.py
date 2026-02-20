"""Authentication CDK stack for the Realtime Agentic API.

Provisions Lambda authorizer functions and supporting Secrets Manager
entries used by API Gateway to authenticate requests via API keys or
JWT bearer tokens.
"""

from __future__ import annotations

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack, Tags
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_cdk import aws_ssm as ssm
from constructs import Construct

from infra.config import EnvironmentConfig


class AuthStack(Stack):
    """Lambda authorizers and secrets for API Gateway authentication."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        config: EnvironmentConfig,
        **kwargs: object,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self._config = config

        for key, value in config.tags.items():
            Tags.of(self).add(key, value)

        # --- Secrets ---
        self.api_keys_secret = self._create_secret(
            "api-keys", "API key mappings for API key authorization"
        )
        self.jwt_secret = self._create_secret(
            "jwt-signing-key", "JWT signing key for token authorization"
        )

        # --- Lambda Authorizers ---
        self.api_key_authorizer_fn = self._create_api_key_authorizer()
        self.jwt_authorizer_fn = self._create_jwt_authorizer()

        # --- SSM Parameters ---
        self._publish_ssm_params()

        # --- Outputs ---
        self._create_outputs()

    # ------------------------------------------------------------------
    # Secrets
    # ------------------------------------------------------------------

    def _create_secret(self, name: str, description: str) -> secretsmanager.Secret:
        return secretsmanager.Secret(
            self,
            f"Secret-{name}",
            secret_name=f"{self._config.secrets_prefix}/{self._config.stage}/{name}",
            description=f"{description} for {self._config.stage} environment",
            removal_policy=(
                RemovalPolicy.DESTROY if self._config.stage == "dev" else RemovalPolicy.RETAIN
            ),
        )

    # ------------------------------------------------------------------
    # Lambda Authorizers
    # ------------------------------------------------------------------

    def _create_api_key_authorizer(self) -> _lambda.Function:
        """Create the API-key authorizer Lambda function."""
        fn = _lambda.Function(
            self,
            "ApiKeyAuthorizerFn",
            function_name=self._config.resource_name("api-key-authorizer"),
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="runtime.auth.api_key_authorizer.handler",
            code=_lambda.Code.from_asset("."),
            memory_size=self._config.lambda_memory_mb,
            timeout=Duration.seconds(self._config.lambda_timeout_seconds),
            environment={
                "STAGE": self._config.stage,
                "API_KEYS_SECRET_NAME": self.api_keys_secret.secret_name,
            },
            description="API Key authorizer for API Gateway",
        )
        self.api_keys_secret.grant_read(fn)
        return fn

    def _create_jwt_authorizer(self) -> _lambda.Function:
        """Create the JWT authorizer Lambda function."""
        fn = _lambda.Function(
            self,
            "JwtAuthorizerFn",
            function_name=self._config.resource_name("jwt-authorizer"),
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="runtime.auth.jwt_authorizer.handler",
            code=_lambda.Code.from_asset("."),
            memory_size=self._config.lambda_memory_mb,
            timeout=Duration.seconds(self._config.lambda_timeout_seconds),
            environment={
                "STAGE": self._config.stage,
                "JWT_SECRET_NAME": self.jwt_secret.secret_name,
            },
            description="JWT authorizer for API Gateway",
        )
        self.jwt_secret.grant_read(fn)
        return fn

    # ------------------------------------------------------------------
    # SSM Parameters
    # ------------------------------------------------------------------

    def _publish_ssm_params(self) -> None:
        prefix = f"/{self._config.resource_prefix}"

        ssm.StringParameter(
            self,
            "SsmApiKeyAuthorizerArn",
            parameter_name=f"{prefix}/api-key-authorizer-arn",
            string_value=self.api_key_authorizer_fn.function_arn,
            description="API Key authorizer Lambda ARN",
        )

        ssm.StringParameter(
            self,
            "SsmJwtAuthorizerArn",
            parameter_name=f"{prefix}/jwt-authorizer-arn",
            string_value=self.jwt_authorizer_fn.function_arn,
            description="JWT authorizer Lambda ARN",
        )

        ssm.StringParameter(
            self,
            "SsmApiKeysSecretArn",
            parameter_name=f"{prefix}/api-keys-secret-arn",
            string_value=self.api_keys_secret.secret_arn,
            description="API keys secret ARN",
        )

        ssm.StringParameter(
            self,
            "SsmJwtSecretArn",
            parameter_name=f"{prefix}/jwt-secret-arn",
            string_value=self.jwt_secret.secret_arn,
            description="JWT signing key secret ARN",
        )

    # ------------------------------------------------------------------
    # Outputs
    # ------------------------------------------------------------------

    def _create_outputs(self) -> None:
        CfnOutput(
            self,
            "ApiKeyAuthorizerFnArn",
            value=self.api_key_authorizer_fn.function_arn,
            description="API Key authorizer Lambda ARN",
        )
        CfnOutput(
            self,
            "JwtAuthorizerFnArn",
            value=self.jwt_authorizer_fn.function_arn,
            description="JWT authorizer Lambda ARN",
        )
        CfnOutput(
            self,
            "ApiKeysSecretArn",
            value=self.api_keys_secret.secret_arn,
            description="API keys secret ARN",
        )
        CfnOutput(
            self,
            "JwtSecretArn",
            value=self.jwt_secret.secret_arn,
            description="JWT signing key secret ARN",
        )
