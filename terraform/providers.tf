# Define required providers
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws" # Official AWS provider
      version = "~> 5.0"        # Use version 5.x
    }
  }
}

# Configure AWS provider
provider "aws" {
  region  = var.aws_region # AWS region (we can change later)
  profile = var.aws_profile # Optional local AWS profile; null lets the SDK/provider chain resolve dynamically
}

