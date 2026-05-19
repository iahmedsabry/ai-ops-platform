# PER-ENVIRONMENT (Terraform): region, project_name, and network CIDRs must match the target AWS account / VPC design.
aws_region   = "us-east-1"        # AWS region
project_name = "ai-ops-platform"  # Project name (prefix for many resource names)

aws_profile = "hands-on" # Optional for local Terraform runs; leave unset in automation

vpc_cidr = "10.0.0.0/16"

public_subnets = [
  "10.0.1.0/24",
  "10.0.2.0/24"
]

private_subnets = [
  "10.0.10.0/24",
  "10.0.11.0/24"
]