#!/usr/bin/env python3
import os
import toml
import aws_cdk as cdk
from urupraxis_secure_cicd_pipeline.pipeline_stack import PipelineStack

app = cdk.App()

# =========================================================
# RUNTIME CONFIGURATION INITIALIZATION
# =========================================================
config_path = os.path.join(os.path.dirname(__file__), "config.toml")
config = toml.load(config_path)

# Fallback to TOML [ENV] table if inline CDK_ENV is missing
target_env = os.getenv("CDK_ENV", config["ENV"]["ENVIRONMENT"])
global_section = f"GLOBAL_{target_env}"

aws_env = cdk.Environment(
    account=config[global_section]["ACCOUNT"],
    region=config[global_section]["REGION"]
)

# =========================================================
# SINGLE-STACK ARCHITECTURE INSTANTIATION
# =========================================================
pipeline_stack = PipelineStack(
    app, f"UruPraxis-DevSecOpsPipeline-{target_env.capitalize()}",
    env=aws_env,
    environment=target_env
)

# Enforce resource tags injection across the entire ecosystem driven by TOML data
if "tags" in config[global_section]:
    for key, value in config[global_section]["tags"].items():
        cdk.Tags.of(pipeline_stack).add(key, value)

app.synth()
