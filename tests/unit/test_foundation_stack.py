"""Unit tests for the Foundation CDK stack."""

import aws_cdk as cdk
from aws_cdk.assertions import Template

from infra.config import EnvironmentConfig
from infra.foundation_stack import FoundationStack


def _synth_template(config: EnvironmentConfig) -> Template:
    app = cdk.App()
    stack = FoundationStack(
        app,
        "TestFoundation",
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


class TestFoundationStackDev:
    """Tests for the dev environment foundation stack."""

    def test_vpc_created(self) -> None:
        template = _synth_template(_dev_config())
        template.resource_count_is("AWS::EC2::VPC", 1)

    def test_vpc_cidr(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::EC2::VPC",
            {"CidrBlock": "10.0.0.0/16"},
        )

    def test_no_nat_gateways_in_dev(self) -> None:
        template = _synth_template(_dev_config())
        template.resource_count_is("AWS::EC2::NatGateway", 0)

    def test_lambda_security_group_created(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::EC2::SecurityGroup",
            {
                "GroupDescription": "Security group for Lambda functions",
            },
        )

    def test_cache_security_group_created(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::EC2::SecurityGroup",
            {
                "GroupDescription": "Security group for ElastiCache cluster",
            },
        )

    def test_secrets_created(self) -> None:
        template = _synth_template(_dev_config())
        template.resource_count_is("AWS::SecretsManager::Secret", 2)

    def test_openai_secret_name(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::SecretsManager::Secret",
            {"Name": "realtime-agentic-api/dev/openai-api-key"},
        )

    def test_anthropic_secret_name(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::SecretsManager::Secret",
            {"Name": "realtime-agentic-api/dev/anthropic-api-key"},
        )

    def test_ssm_parameters_created(self) -> None:
        template = _synth_template(_dev_config())
        template.resource_count_is("AWS::SSM::Parameter", 5)

    def test_outputs_present(self) -> None:
        template = _synth_template(_dev_config())
        template.has_output("VpcId", {"Description": "VPC ID"})
        template.has_output(
            "LambdaSecurityGroupId",
            {"Description": "Lambda security group ID"},
        )


class TestFoundationStackProd:
    """Tests for the prod environment foundation stack."""

    def test_nat_gateways_in_prod(self) -> None:
        template = _synth_template(_prod_config())
        template.resource_count_is("AWS::EC2::NatGateway", 2)

    def test_flow_log_in_prod(self) -> None:
        template = _synth_template(_prod_config())
        template.resource_count_is("AWS::EC2::FlowLog", 1)

    def test_secrets_retained_in_prod(self) -> None:
        template = _synth_template(_prod_config())
        template.has_resource(
            "AWS::SecretsManager::Secret",
            {
                "DeletionPolicy": "Retain",
                "UpdateReplacePolicy": "Retain",
            },
        )
