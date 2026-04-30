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

# VPC CIDR block (main network range)
variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
}

# Public subnet CIDRs
variable "public_subnets" {
  description = "List of public subnet CIDRs"
  type        = list(string)
}

# Private subnet CIDRs
variable "private_subnets" {
  description = "List of private subnet CIDRs"
  type        = list(string)
}