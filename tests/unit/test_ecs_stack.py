import json

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
    template = _ecs_template(True)
    (resource,) = template.find_resources("Custom::AWS").values()
    create = json.dumps(resource["Properties"]["Create"])
    assert "putRetentionPolicy" in create
    assert '\\"retentionInDays\\":365' in create
    # The custom resource handler's own log group must also be retained a year.
    template.resource_count_is("Custom::LogRetention", 0)
    for log_group in template.find_resources("AWS::Logs::LogGroup").values():
        assert log_group["Properties"]["RetentionInDays"] == 365


def test_no_log_retention_without_container_insights():
    template = _ecs_template(False)
    template.resource_count_is("Custom::AWS", 0)
    template.resource_count_is("AWS::Logs::LogGroup", 0)
