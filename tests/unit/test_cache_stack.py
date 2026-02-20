"""Unit tests for the Cache CDK stack."""

import aws_cdk as cdk
from aws_cdk.assertions import Template

from infra.cache_stack import CacheStack
from infra.config import EnvironmentConfig
from infra.foundation_stack import FoundationStack


def _synth_template(config: EnvironmentConfig) -> Template:
    app = cdk.App()
    env = cdk.Environment(account=config.aws_account_id, region=config.aws_region)

    foundation = FoundationStack(
        app,
        "TestFoundation",
        config=config,
        env=env,
    )

    cache_stack = CacheStack(
        app,
        "TestCache",
        config=config,
        vpc=foundation.vpc,
        cache_security_group=foundation.cache_sg,
        env=env,
    )

    return Template.from_stack(cache_stack)
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
        cache_node_type="cache.t3.small",
        tags={"Environment": "prod"},
    )
class TestCacheStackCluster:
    """Tests that ElastiCache Redis cluster is created correctly."""

    def test_redis_cluster_created(self) -> None:
        template = _synth_template(_dev_config())
        template.resource_count_is("AWS::ElastiCache::CacheCluster", 1)

    def test_redis_engine(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::ElastiCache::CacheCluster",
            {"Engine": "redis"},
        )

    def test_redis_version(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::ElastiCache::CacheCluster",
            {"EngineVersion": "7.1"},
        )

    def test_dev_node_type(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::ElastiCache::CacheCluster",
            {"CacheNodeType": "cache.t3.micro"},
        )

    def test_prod_node_type(self) -> None:
        template = _synth_template(_prod_config())
        template.has_resource_properties(
            "AWS::ElastiCache::CacheCluster",
            {"CacheNodeType": "cache.t3.small"},
        )

    def test_single_node(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::ElastiCache::CacheCluster",
            {"NumCacheNodes": 1},
        )

    def test_redis_port(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::ElastiCache::CacheCluster",
            {"Port": 6379},
        )
class TestCacheStackSubnetGroup:
    """Tests for ElastiCache subnet group."""

    def test_subnet_group_created(self) -> None:
        template = _synth_template(_dev_config())
        template.resource_count_is("AWS::ElastiCache::SubnetGroup", 1)

    def test_subnet_group_name(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::ElastiCache::SubnetGroup",
            {"CacheSubnetGroupName": "realtime-agentic-api-dev-cache-subnet-group"},
        )
class TestCacheStackSnapshots:
    """Tests for snapshot configuration."""

    def test_dev_no_snapshots(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::ElastiCache::CacheCluster",
            {"SnapshotRetentionLimit": 0},
        )

    def test_prod_snapshots_enabled(self) -> None:
        template = _synth_template(_prod_config())
        template.has_resource_properties(
            "AWS::ElastiCache::CacheCluster",
            {"SnapshotRetentionLimit": 7},
        )
class TestCacheStackRemovalPolicy:
    """Tests for removal policy configuration."""

    def test_dev_cluster_deleted_on_stack_removal(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource(
            "AWS::ElastiCache::CacheCluster",
            {
                "DeletionPolicy": "Delete",
                "UpdateReplacePolicy": "Delete",
            },
        )

    def test_prod_cluster_retained(self) -> None:
        template = _synth_template(_prod_config())
        template.has_resource(
            "AWS::ElastiCache::CacheCluster",
            {
                "DeletionPolicy": "Retain",
                "UpdateReplacePolicy": "Retain",
            },
        )
class TestCacheStackSSMParams:
    """Tests for SSM parameter publishing."""

    def test_ssm_parameters_created(self) -> None:
        template = _synth_template(_dev_config())
        # 2 parameters: endpoint and port
        template.resource_count_is("AWS::SSM::Parameter", 2)
class TestCacheStackOutputs:
    """Tests for stack outputs."""

    def test_outputs_present(self) -> None:
        template = _synth_template(_dev_config())
        template.has_output("CacheClusterEndpoint", {})
        template.has_output("CacheClusterPort", {})
        template.has_output("CacheClusterName", {})
