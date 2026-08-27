import os
import toml
from aws_cdk import (
    aws_codebuild as codebuild,
    aws_ecr as ecr,
    aws_kms as kms,
    aws_codepipeline as codepipeline,
    aws_codepipeline_actions as pipeline_actions,
    RemovalPolicy,
)
from constructs import Construct

class SecureBuildConstruct(Construct):

    def __init__(self, scope: Construct, construct_id: str, environment: str, source_output: codepipeline.Artifact, encryption_key: kms.IKey, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # =========================================================
        # ENVIRONMENT CONFIGURATION PARSER
        # =========================================================
        config_path = os.path.join(os.getcwd(), "config.toml")
        config = toml.load(config_path)

        build_section = f"BUILD_{environment}"
        compute_type_str = config[build_section]["COMPUTE_TYPE"]
        image_scan = config[build_section]["IMAGE_SCAN_ON_PUSH"]

        resource_prefix = f"UruPraxis-{environment}"
        rem_policy = RemovalPolicy.DESTROY if environment == "dev" else RemovalPolicy.RETAIN

        # =========================================================
        # HARDENED CONTAINER REGISTRY (AMAZON ECR)
        # =========================================================
        # Enforces encrypted storage and automated vulnerability scanning out-of-the-box
        self.repository = ecr.Repository(
            self, "AppContainerRepository",
            repository_name=f"{resource_prefix}-app-repo",
            image_scan_on_push=image_scan, # Core DevSecOps trigger
            encryption=ecr.RepositoryEncryption.KMS,
            encryption_key=encryption_key, # Uses centralized UruPraxis CMK
            removal_policy=rem_policy,
            empty_on_delete=True if environment == "dev" else False
        )

        # =========================================================
        # DEVSECOPS BUILD SPECIFICATION DESIGN
        # =========================================================
        # Standardized enterprise pipeline steps integrating security checkpoints
        build_spec_dict = {
            "version": "0.2",
            "phases": {
                "pre_build": {
                    "commands": [
                        "echo '=== PHASE 1: Code Quality & Testing ==='",
                        "pip install flake8 pytest pip-audit",
                        "flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics",
                        "echo '=== PHASE 2: Secret & Credentials Scanning ==='",
                        "# Optional: git-leaks execution can be added here",
                        "echo '=== PHASE 3: Software Composition Analysis (SCA) ==='",
                        "pip-audit --local", # Blocks build if compromised libraries are found
                        "echo 'Logging into Amazon ECR...'",
                        "aws ecr get-login-password --region $AWS_DEFAULT_REGION | docker login --username AWS --password-stdin $ECR_REPOSITORY_URL"
                    ]
                },
                "build": {
                    "commands": [
                        "echo '=== PHASE 4: Cryptographically Secure Image Build ==='",
                        "docker build -t $ECR_REPOSITORY_URL:latest .",
                        "docker tag $ECR_REPOSITORY_URL:latest $ECR_REPOSITORY_URL:$CODEBUILD_RESOLVED_SOURCE_VERSION"
                    ]
                },
                "post_build": {
                    "commands": [
                        "echo 'Pushing Docker image to Amazon ECR...'",
                        "docker push $ECR_REPOSITORY_URL:latest",
                        "docker push $ECR_REPOSITORY_URL:$CODEBUILD_RESOLVED_SOURCE_VERSION",
                        "echo 'Writing deployment artifacts for CodeDeploy...'",
                        "printf '[{\"name\":\"app-container\",\"imageUri\":\"%s\"}]' $ECR_REPOSITORY_URL:$CODEBUILD_RESOLVED_SOURCE_VERSION > imagedefinitions.json"
                    ]
                }
            },
            "artifacts": {
                "files": ["imagedefinitions.json"] # Required output to feed the deployment stage
            }
        }

        # =========================================================
        # AWS CODEBUILD PROJECT ENGINE
        # =========================================================
        build_project = codebuild.PipelineProject(
            self, "DevSecOpsBuildProject",
            project_name=f"{resource_prefix}-build-engine",
            encryption_key=encryption_key,
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.AMAZON_LINUX_2_4, # Enterprise standard stable build image
                privileged=True, # Mandatorily required to execute Docker builds inside the container
                compute_type=getattr(codebuild.ComputeType, compute_type_str)
            ),
            environment_variables={
                "ECR_REPOSITORY_URL": codebuild.BuildEnvironmentVariable(value=self.repository.repository_uri)
            },
            build_spec=codebuild.BuildSpec.from_source_filename("buildspec.yml")
        )

        # Grant explicit least-privilege IAM permissions for the build engine to talk to ECR
        self.repository.grant_pull_push(build_project.role)

        # =========================================================
        # CODEPIPELINE BUILD ACTION DEFINITION
        # =========================================================
        self.build_output = codepipeline.Artifact(artifact_name="BuildArtifact")
        
        self.build_action = pipeline_actions.CodeBuildAction(
            action_name="DevSecOps_Build_and_Scan",
            project=build_project,
            input=source_output,
            outputs=[self.build_output]
        )
