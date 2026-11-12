import aws_cdk as cdk
import aws_cdk.assertions as assertions

from src.ecs_stack import EcsStack
from src.network_stack import NetworkStack


def _ecs_template(container_insights):
    app = cdk.App()
    network = NetworkStack(app, "Net", vpc_cidr="10.0.0.0/24")
    ecs = EcsStack(
        app,
        "Ecs",
        vpc=network.vpc,
        namespace="test.io",
        container_insights=container_insights,
    )
    return assertions.Template.from_stack(ecs)


def test_container_insights_log_group_retained_one_year():
    _ecs_template(True).has_resource_properties(
        "Custom::LogRetention", {"RetentionInDays": 365}
    )


def test_no_log_retention_without_container_insights():
    _ecs_template(False).resource_count_is("Custom::LogRetention", 0)
