import aws_cdk as cdk

from aws_cdk import (
    aws_ec2 as ec2,
    aws_elasticache as elasticache,
)

from constructs import Construct


class RedisStack(cdk.Stack):
    """
    ElastiCache Serverless Valkey cache for session storage and client registry
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.Vpc,
        engine_version: str = "8.2",
        max_ecpu_per_second: int = 1000,
        max_storage_gb: int = 1,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # -------------------
        # Security Group for Valkey Serverless
        # -------------------
        self.redis_security_group = ec2.SecurityGroup(
            self,
            "RedisSecurityGroup",
            vpc=vpc,
            description="Security group for ElastiCache Serverless Valkey",
            allow_all_outbound=False,
        )

        # Allow inbound Valkey traffic from VPC CIDR (avoids circular dependency with app stack)
        self.redis_security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(6379),
            description="Allow Valkey traffic from VPC",
        )

        # -------------------
        # ElastiCache Serverless Valkey Cache
        # -------------------
        self.serverless_cache = elasticache.CfnServerlessCache(
            self,
            "ValkeyServerlessCache",
            serverless_cache_name=f"{construct_id}-cache",
            description=f"Serverless Valkey cache for Synapse MCP - {construct_id}",
            engine="valkey",
            major_engine_version=engine_version.split(".")[
                0
            ],  # Extract major version (e.g., "8" from "8.0")
            security_group_ids=[self.redis_security_group.security_group_id],
            subnet_ids=[subnet.subnet_id for subnet in vpc.private_subnets],
            cache_usage_limits=elasticache.CfnServerlessCache.CacheUsageLimitsProperty(
                data_storage=elasticache.CfnServerlessCache.DataStorageProperty(
                    maximum=max_storage_gb, unit="GB"
                ),
                ecpu_per_second=elasticache.CfnServerlessCache.ECPUPerSecondProperty(
                    maximum=max_ecpu_per_second
                ),
            ),
            snapshot_retention_limit=7,
            daily_snapshot_time="03:00",
        )

        # Get the endpoint from the serverless cache
        redis_endpoint = self.serverless_cache.attr_endpoint_address
        redis_port = self.serverless_cache.attr_endpoint_port

        # Construct Redis URL (using rediss:// for TLS-enabled connection)
        # Valkey is Redis-compatible, so we use the rediss:// scheme
        redis_url = f"rediss://{redis_endpoint}:{redis_port}"

        # -------------------
        # Outputs
        # -------------------
        cdk.CfnOutput(
            self,
            "RedisEndpoint",
            value=redis_endpoint,
            description="Valkey cluster endpoint",
        )

        cdk.CfnOutput(
            self,
            "RedisPort",
            value=redis_port,
            description="Valkey cluster port",
        )

        cdk.CfnOutput(
            self,
            "RedisUrl",
            value=redis_url,
            description="Valkey connection URL (Redis-compatible)",
        )

        cdk.CfnOutput(
            self,
            "RedisSecurityGroupId",
            value=self.redis_security_group.security_group_id,
            description="Security group ID for Valkey cluster",
        )

        # Store the URL for easy access by other stacks
        self.redis_url = redis_url
