# AWS region variable
variable "aws_region" {
  description = "AWS region to deploy resources"  # Simple explanation
  type        = string                            # Must be a string
}

# Project name (used for naming resources later)
variable "project_name" {
  description = "Project name prefix"
  type        = string
}