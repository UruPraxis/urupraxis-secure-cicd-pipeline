import os
import toml
from aws_cdk import (
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_elasticloadbalancingv2 as elbv2,
    aws_codepipeline as codepipeline,
    aws_codepipeline_actions as pipeline_actions,
    aws_ecs_patterns as ecs_patterns,
    Duration,
)
from constructs import Construct

class SecureDeployConstruct(Construct):

    # FIX: Added 'action_role' directly into the constructor positional parameters
    def __init__(self, scope: Construct, construct_id: str, environment: str, build_output: codepipeline.Artifact, action_role, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # =========================================================
        # ENVIRONMENT CONFIGURATION PARSER
        # =========================================================
        config_path = os.path.join(os.getcwd(), "config.toml")
        config = toml.load(config_path)

        deploy_section = f"DEPLOY_{environment}"
        container_port = config[deploy_section]["CONTAINER_PORT"]
        desired_count = config[deploy_section]["DESIRED_COUNT"]

        resource_prefix = f"UruPraxis-{environment}"

        # =========================================================
        # NETWORK ADAPTATION (LOOKUP OR REUSE CORE NETWORK)
        # =========================================================
        vpc = ec2.Vpc(self, "PipelineTargetVpc", max_azs=2)

        # =========================================================
        # SERVERLESS CONTAINER INFRASTRUCTURE (ECS CLUSTER)
        # =========================================================
        cluster_instance = ecs.Cluster(
            self, "EcsCluster", 
            vpc=vpc, 
            cluster_name=f"{resource_prefix}-ecs-cluster"
        )

        # =========================================================
        # HIGH-LEVEL SERVERLESS CONTAINER & ALB (ECS PATTERNS)
        # =========================================================
        self.fargate_load_balanced_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self, "FargateService",
            cluster=cluster_instance,
            service_name=f"{resource_prefix}-app-service",
            cpu=256,
            memory_limit_mib=512,
            desired_count=desired_count,
            public_load_balancer=True,
            listener_port=80,
            # Enforce 100% task availability during updates to prevent drop in load capacity
            min_healthy_percent=100, # Resolves the 50% unsafe deployment warning
            # Enable native deployment circuit breaker for instant automated rollbacks
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True), # Resolves the 3-hour timeout warning
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_registry("public.ecr.aws/nginx/nginx:alpine"),
                container_name="app-container",
                container_port=container_port
            )
        )

        # Configure Auto-Scaling triggers based on real-time CPU metric usage
        scaling = self.fargate_load_balanced_service.service.auto_scale_task_count(
            max_capacity=5
        )
        scaling.scale_on_cpu_utilization(
            "CpuScaling",
            target_utilization_percent=70,
            scale_in_cooldown=Duration.seconds(60),
            scale_out_cooldown=Duration.seconds(60)
        )

        # =========================================================
        # CONTAINER REGISTRY SECURITY ACCESS PATCH (ECR RO)
        # =========================================================
        # Explicitly grant Amazon ECR Read capabilities to the Fargate Task Execution Role
        if self.fargate_load_balanced_service.task_definition.execution_role:
            # Import standard IAM managed policy inside the execution layer
            from aws_cdk import aws_iam as iam
            self.fargate_load_balanced_service.task_definition.execution_role.add_managed_policy(
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2ContainerRegistryReadOnly")
            )

        # =========================================================
        # CODEPIPELINE DEPLOY ACTION DEFINITION
        # =========================================================
        self.deploy_action = pipeline_actions.EcsDeployAction(
            action_name="Automated_ECS_Deployment",
            service=self.fargate_load_balanced_service.service,
            input=build_output,
            role=action_role # <-- FIX: Bind our custom authorized role directly to the execution engine
        )
