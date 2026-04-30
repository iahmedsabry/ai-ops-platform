aws_region   = "us-east-1"        # AWS region
project_name = "ai-ops-platform"  # Project name

vpc_cidr = "10.0.0.0/16"

public_subnets = [
  "10.0.1.0/24",
  "10.0.2.0/24"
]

private_subnets = [
  "10.0.10.0/24",
  "10.0.11.0/24"
]