"""Foundation CDK stack: VPC, networking, secrets, and shared resources.

This stack provisions the base infrastructure that all other stacks depend on:
- VPC with public/private subnets (optional NAT gateways per environment)
- Security groups for Lambda, cache, and internal traffic
- Secrets Manager entries for LLM provider API keys
- SSM parameters for cross-stack references
"""

from __future__ import annotations

from aws_cdk import CfnOutput, RemovalPolicy, Stack, Tags
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_cdk import aws_ssm as ssm
from constructs import Construct

from infra.config import EnvironmentConfig


class FoundationStack(Stack):
    """Base infrastructure stack for the Realtime Agentic API."""

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

        # Apply tags to all resources in the stack
        for key, value in config.tags.items():
            Tags.of(self).add(key, value)

        # --- VPC ---
        self.vpc = self._create_vpc()

        # --- Security Groups ---
        self.lambda_sg = self._create_lambda_security_group()
        self.cache_sg = self._create_cache_security_group()

        # --- Secrets ---
        self.openai_secret = self._create_secret("openai-api-key", "OpenAI API key")
        self.anthropic_secret = self._create_secret("anthropic-api-key", "Anthropic API key")

        # --- SSM Parameters (cross-stack references) ---
        self._publish_ssm_params()

        # --- Outputs ---
        self._create_outputs()

    # VPC

    def _create_vpc(self) -> ec2.Vpc:
        subnet_config: list[ec2.SubnetConfiguration] = [
            ec2.SubnetConfiguration(
                name="Public",
                subnet_type=ec2.SubnetType.PUBLIC,
                cidr_mask=24,
            ),
        ]

        # Only create private subnets when we have NAT gateways (staging/prod)
        if self._config.nat_gateways > 0:
            subnet_config.append(
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                )
            )
        else:
            # Dev environment: use isolated subnets (no internet egress)
            subnet_config.append(
                ec2.SubnetConfiguration(
                    name="Isolated",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                )
            )

        vpc = ec2.Vpc(
            self,
            "Vpc",
            vpc_name=self._config.resource_name("vpc"),
            ip_addresses=ec2.IpAddresses.cidr(self._config.vpc_cidr),
            max_azs=self._config.max_azs,
            nat_gateways=self._config.nat_gateways,
            subnet_configuration=subnet_config,
        )

        # VPC Flow Logs for prod/staging
        if self._config.stage != "dev":
            vpc.add_flow_log("FlowLog")

        return vpc

    # Security Groups

    def _create_lambda_security_group(self) -> ec2.SecurityGroup:
        sg = ec2.SecurityGroup(
            self,
            "LambdaSg",
            vpc=self.vpc,
            security_group_name=self._config.resource_name("lambda-sg"),
            description="Security group for Lambda functions",
            allow_all_outbound=True,
        )
        return sg

    def _create_cache_security_group(self) -> ec2.SecurityGroup:
        sg = ec2.SecurityGroup(
            self,
            "CacheSg",
            vpc=self.vpc,
            security_group_name=self._config.resource_name("cache-sg"),
            description="Security group for ElastiCache cluster",
            allow_all_outbound=False,
        )
        # Allow inbound Redis traffic from Lambda functions
        sg.add_ingress_rule(
            peer=self.lambda_sg,
            connection=ec2.Port.tcp(6379),
            description="Allow Redis from Lambda",
        )
        return sg

    # Secrets Manager

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

    # SSM Parameters (for cross-stack references)

    def _publish_ssm_params(self) -> None:
        prefix = f"/{self._config.resource_prefix}"

        ssm.StringParameter(
            self,
            "SsmVpcId",
            parameter_name=f"{prefix}/vpc-id",
            string_value=self.vpc.vpc_id,
            description="VPC ID for the Realtime Agentic API",
        )

        ssm.StringParameter(
            self,
            "SsmLambdaSgId",
            parameter_name=f"{prefix}/lambda-sg-id",
            string_value=self.lambda_sg.security_group_id,
            description="Lambda security group ID",
        )

        ssm.StringParameter(
            self,
            "SsmCacheSgId",
            parameter_name=f"{prefix}/cache-sg-id",
            string_value=self.cache_sg.security_group_id,
            description="Cache security group ID",
        )

        ssm.StringParameter(
            self,
            "SsmOpenAiSecretArn",
            parameter_name=f"{prefix}/openai-secret-arn",
            string_value=self.openai_secret.secret_arn,
            description="OpenAI API key secret ARN",
        )

        ssm.StringParameter(
            self,
            "SsmAnthropicSecretArn",
            parameter_name=f"{prefix}/anthropic-secret-arn",
            string_value=self.anthropic_secret.secret_arn,
            description="Anthropic API key secret ARN",
        )

    # Outputs

    def _create_outputs(self) -> None:
        CfnOutput(self, "VpcId", value=self.vpc.vpc_id, description="VPC ID")
        CfnOutput(
            self,
            "LambdaSecurityGroupId",
            value=self.lambda_sg.security_group_id,
            description="Lambda security group ID",
        )
        CfnOutput(
            self,
            "CacheSecurityGroupId",
            value=self.cache_sg.security_group_id,
            description="Cache security group ID",
        )
        CfnOutput(
            self,
            "OpenAiSecretArn",
            value=self.openai_secret.secret_arn,
            description="OpenAI API key secret ARN",
        )
        CfnOutput(
            self,
            "AnthropicSecretArn",
            value=self.anthropic_secret.secret_arn,
            description="Anthropic API key secret ARN",
        )
