import aws_cdk as core
import aws_cdk.assertions as assertions

from urupraxis_secure_cicd_pipeline.pipeline_stack import UrupraxisSecureCicdPipelineStack

# example tests. To run these tests, uncomment this file along with the example
# resource in urupraxis_secure_cicd_pipeline/urupraxis_secure_cicd_pipeline_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = UrupraxisSecureCicdPipelineStack(app, "urupraxis-secure-cicd-pipeline")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
