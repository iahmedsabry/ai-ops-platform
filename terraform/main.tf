# Create a simple VPC (network in AWS)
resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"  # IP range for the network

  tags = {
    Name = "${var.project_name}-vpc"  # Name of the VPC
  }
}