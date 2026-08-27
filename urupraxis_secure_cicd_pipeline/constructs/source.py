import os
import toml
from aws_cdk import (
    aws_codestarconnections as codestar, # Reliable native connection resource
    aws_codepipeline as codepipeline,
    aws_codepipeline_actions as pipeline_actions,
)
from constructs import Construct

class SecureSourceConstruct(Construct):

    def __init__(self, scope: Construct, construct_id: str, environment: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # =========================================================
        # ENVIRONMENT CONFIGURATION PARSER
        # =========================================================
        config_path = os.path.join(os.getcwd(), "config.toml")
        config = toml.load(config_path)

        source_section = f"SOURCE_{environment}"
        github_repo = config[source_section]["GITHUB_REPOSITORY"]
        github_branch = config[source_section]["GITHUB_BRANCH"]

        resource_prefix = f"UruPraxis-{environment}"

        # =========================================================
        # AUTOMATED RESOURCE PROVISIONING (IaC Connection)
        # =========================================================
        # This instructs AWS to create the connection asset dynamically inside the account
        self.connection = codestar.CfnConnection(
            self, "GitHubConnectionResource",
            connection_name=f"{resource_prefix}-github-link",
            provider_type="GitHub"
        )

        # =========================================================
        # CODEPIPELINE SOURCE ACTION DEFINITION
        # =========================================================
        self.source_output = codepipeline.Artifact(artifact_name="SourceArtifact")

        # Parse organization/owner and repository name using explicit array indexing
        repo_parts = github_repo.split("/")
        repo_owner = repo_parts[0]  # Extracts "UruPraxis"
        repo_name = repo_parts[1]   # Extracts "sample-app"

        self.source_action = pipeline_actions.CodeStarConnectionsSourceAction(
            action_name="GitHub_Source",
            owner=repo_owner,
            repo=repo_name,
            branch=github_branch,
            # MAGIC INJECTION: We fetch the dynamic ARN generated during cloud deployment in mid-air
            connection_arn=self.connection.attr_connection_arn,
            output=self.source_output,
            trigger_on_push=True
        )
