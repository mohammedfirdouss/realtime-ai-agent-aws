"""ElastiCache Redis CDK stack for the Realtime Agentic API.

Defines ElastiCache Redis cluster with:
- Configurable node type and replica count per environment
- VPC subnet group for private placement
- Security group ingress from Lambda functions
- SSM parameters for endpoint discovery
"""

from __future__ import annotations

from aws_cdk import CfnOutput, RemovalPolicy, Stack, Tags
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_elasticache as elasticache
from aws_cdk import aws_ssm as ssm
from constructs import Construct

from infra.config import EnvironmentConfig


class CacheStack(Stack):
    """ElastiCache Redis cluster for the Realtime Agentic API."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        config: EnvironmentConfig,
        vpc: ec2.IVpc,
        cache_security_group: ec2.ISecurityGroup,
        **kwargs: object,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self._config = config
        self._vpc = vpc
        self._cache_sg = cache_security_group

        for key, value in config.tags.items():
            Tags.of(self).add(key, value)

        # --- Subnet Group ---
        self.subnet_group = self._create_subnet_group()

        # --- Redis Cluster ---
        self.cache_cluster = self._create_redis_cluster()

        # --- SSM Parameters ---
        self._publish_ssm_params()

        # --- Outputs ---
        self._create_outputs()

    # Subnet Group

    def _create_subnet_group(self) -> elasticache.CfnSubnetGroup:
        """Create a subnet group for ElastiCache placement.

        Uses private/isolated subnets based on environment configuration.
        """
        # Get private or isolated subnets based on environment
        if self._config.nat_gateways > 0:
            subnets = self._vpc.select_subnets(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ).subnet_ids
        else:
            subnets = self._vpc.select_subnets(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ).subnet_ids

        subnet_group = elasticache.CfnSubnetGroup(
            self,
            "CacheSubnetGroup",
            description=f"Subnet group for {self._config.resource_prefix} Redis cluster",
            subnet_ids=subnets,
            cache_subnet_group_name=self._config.resource_name("cache-subnet-group"),
        )

        return subnet_group

    # Redis Cluster

    def _create_redis_cluster(self) -> elasticache.CfnCacheCluster:
        """Create ElastiCache Redis cluster.

        Configuration varies by environment:
        - dev: Single node, cache.t3.micro, no snapshots
        - staging: Single node, cache.t3.micro, daily snapshots
        - prod: Larger node type, daily snapshots, multi-AZ ready

        Note: This stack uses CfnCacheCluster without in-transit or at-rest
        encryption/auth. For sensitive data, prefer a CfnReplicationGroup
        configured with encryption and an auth token.
        """
        # Determine snapshot retention
        snapshot_retention = 0 if self._config.stage == "dev" else 7

        cluster = elasticache.CfnCacheCluster(
            self,
            "RedisCluster",
            cluster_name=self._config.resource_name("redis"),
            engine="redis",
            engine_version="7.1",
            cache_node_type=self._config.cache_node_type,
            num_cache_nodes=self._config.cache_num_nodes,
            cache_subnet_group_name=self.subnet_group.cache_subnet_group_name,
            vpc_security_group_ids=[self._cache_sg.security_group_id],
            port=6379,
            snapshot_retention_limit=snapshot_retention,
            preferred_maintenance_window="sun:05:00-sun:06:00",
            auto_minor_version_upgrade=True,
        )

        # Add dependency on subnet group
        cluster.add_dependency(self.subnet_group)

        # Apply removal policy
        if self._config.stage == "dev":
            cluster.apply_removal_policy(RemovalPolicy.DESTROY)
        else:
            cluster.apply_removal_policy(RemovalPolicy.RETAIN)

        return cluster

    # SSM Parameters

    def _publish_ssm_params(self) -> None:
        """Publish cache cluster endpoint to SSM for Lambda discovery."""
        prefix = f"/{self._config.resource_prefix}"

        ssm.StringParameter(
            self,
            "SsmCacheEndpoint",
            parameter_name=f"{prefix}/cache-endpoint",
            string_value=self.cache_cluster.attr_redis_endpoint_address,
            description="Redis cache cluster endpoint address",
        )

        ssm.StringParameter(
            self,
            "SsmCachePort",
            parameter_name=f"{prefix}/cache-port",
            string_value=self.cache_cluster.attr_redis_endpoint_port,
            description="Redis cache cluster endpoint port",
        )

    # Outputs

    def _create_outputs(self) -> None:
        """Create CloudFormation outputs for cache cluster details."""
        CfnOutput(
            self,
            "CacheClusterEndpoint",
            value=self.cache_cluster.attr_redis_endpoint_address,
            description="Redis cache cluster endpoint address",
        )
        CfnOutput(
            self,
            "CacheClusterPort",
            value=self.cache_cluster.attr_redis_endpoint_port,
            description="Redis cache cluster endpoint port",
        )
        CfnOutput(
            self,
            "CacheClusterName",
            value=self.cache_cluster.cluster_name or "",
            description="Redis cache cluster name",
        )
