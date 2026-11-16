import aws_cdk as cdk

from aws_cdk import (
    aws_ecs as ecs,
    aws_ec2 as ec2,
    aws_logs as logs,
    custom_resources as cr,
)

from constructs import Construct


class EcsStack(cdk.Stack):
    """
    ECS cluster
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.Vpc,
        namespace: str,
        container_insights: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.cluster = ecs.Cluster(
            self,
            "Cluster",
            vpc=vpc,
            default_cloud_map_namespace=ecs.CloudMapNamespaceOptions(
                name=namespace,
                use_for_service_connect=True,
            ),
            container_insights_v2=(
                ecs.ContainerInsights.ENHANCED
                if container_insights
                else ecs.ContainerInsights.DISABLED
            ),
        )

        if container_insights:
            log_group_name = (
                f"/aws/ecs/containerinsights/{self.cluster.cluster_name}/performance"
            )
            put_retention = cr.AwsSdkCall(
                service="CloudWatchLogs",
                action="putRetentionPolicy",
                parameters={
                    "logGroupName": log_group_name,
                    "retentionInDays": 365,
                },
                physical_resource_id=cr.PhysicalResourceId.of(log_group_name),
            )
            cr.AwsCustomResource(
                self,
                "ContainerInsightsRetentionPolicy",
                on_create=put_retention,
                on_update=put_retention,
                install_latest_aws_sdk=False,
                policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
                    resources=[
                        cdk.Stack.of(self).format_arn(
                            service="logs",
                            resource="log-group",
                            resource_name=f"{log_group_name}:*",
                            arn_format=cdk.ArnFormat.COLON_RESOURCE_NAME,
                        )
                    ]
                ),
                log_group=logs.LogGroup(
                    self,
                    "ContainerInsightsLogRetentionHandlerLogs",
                    retention=logs.RetentionDays.ONE_YEAR,
                ),
            )
