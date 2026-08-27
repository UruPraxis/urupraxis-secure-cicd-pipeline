import os
import toml
from aws_cdk import (
    Stack,
    aws_codepipeline as codepipeline,
    aws_kms as kms,
    aws_iam as iam,
    RemovalPolicy,
)
from constructs import Construct

# Import UruPraxis custom DevSecOps constructs
from urupraxis_secure_cicd_pipeline.constructs.source import SecureSourceConstruct
from urupraxis_secure_cicd_pipeline.constructs.build import SecureBuildConstruct
from urupraxis_secure_cicd_pipeline.constructs.deploy import SecureDeployConstruct

class PipelineStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, environment: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # =========================================================
        # ENVIRONMENT CONFIGURATION PARSER
        # =========================================================
        config_path = os.path.join(os.getcwd(), "config.toml")
        config = toml.load(config_path)

        global_section = f"GLOBAL_{environment}"
        rem_policy = RemovalPolicy.DESTROY if environment == "dev" else RemovalPolicy.RETAIN

        # =========================================================
        # CENTRALIZED CRYPTOGRAPHY (KMS CMK)
        # =========================================================
        pipeline_key = kms.Key(
            self, "PipelineEncryptionKey",
            alias=f"alias/urupraxis-pipeline-key-{environment}",
            description="Centralized KMS key for UruPraxis DevSecOps pipeline artifacts encryption",
            enable_key_rotation=True,
            removal_policy=rem_policy
        )

        # =========================================================
        # INITIALIZE PIPELINE STAGE CONSTRUCTS
        # =========================================================
        
        # STAGE 1: SOURCE INITIALIZATION (GitHub Connection)
        source_layer = SecureSourceConstruct(
            self, "PipelineSourceLayer",
            environment=environment
        )

        # STAGE 2: BUILD & SECURITY SCAN INITIALIZATION (CodeBuild & ECR)
        build_layer = SecureBuildConstruct(
            self, "PipelineBuildLayer",
            environment=environment,
            source_output=source_layer.source_output,
            encryption_key=pipeline_key
        )

        # =========================================================
        # FIX: EXPLICIT DEPLOY ACTION ROLE PROVISIONING
        # =========================================================
        # This replaces the automated un-escaped role with our own managed profile
        custom_deploy_action_role = iam.Role(
            self, "DevSecOpsCorePipelineAuto",
            assumed_by=iam.ArnPrincipal(f"arn:aws:iam::{self.account}:root"),
            description="Explicit action execution role with S3 and KMS decryption capabilities"
        )

        # STAGE 3: CANARY DEPLOYMENT INITIALIZATION (ECS Fargate)
        deploy_layer = SecureDeployConstruct(
            self, "PipelineDeployLayer",
            environment=environment,
            build_output=build_layer.build_output,
            action_role=custom_deploy_action_role # <-- PASS THE ROLE TO DEPLOY
        )

        # =========================================================
        # AWS CODEPIPELINE CORE ORCHESTRATION ENGINE
        # =========================================================
        self.pipeline = codepipeline.Pipeline(
            self, "DevSecOpsCorePipeline",
            pipeline_name=f"UruPraxis-devsecops-pipeline-{environment}",
            stages=[
                codepipeline.StageProps(
                    stage_name="Source",
                    actions=[source_layer.source_action]
                ),
                codepipeline.StageProps(
                    stage_name="Build_and_Security_Scan",
                    actions=[build_layer.build_action]
                ),
                codepipeline.StageProps(
                    stage_name="Automated_Canary_Deploy",
                    actions=[deploy_layer.deploy_action]
                )
            ]
        )

        # =========================================================
        # SECURITY & IAM LEAST-PRIVILEGE GRANTS
        # =========================================================
        if self.pipeline.artifact_bucket:
            # 1. Grant explicit read/decrypt to the main pipeline role
            self.pipeline.artifact_bucket.grant_read(self.pipeline.role)
            pipeline_key.grant_decrypt(self.pipeline.role)
            
            # 2. FIX: Inject your successful manual permissions to our explicit action role
            self.pipeline.artifact_bucket.grant_read(custom_deploy_action_role)
            pipeline_key.grant_decrypt(custom_deploy_action_role)
            



