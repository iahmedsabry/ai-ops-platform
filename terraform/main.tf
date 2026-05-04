data "aws_availability_zones" "available" {}

# Create VPC using variable instead of hardcoding
resource "aws_vpc" "main" {
  cidr_block = var.vpc_cidr  # Use value from terraform.tfvars

  # Enable DNS (needed later for Kubernetes)
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${var.project_name}-vpc"  # Dynamic naming
  }
}

# Create public subnets
resource "aws_subnet" "public" {
  count = length(var.public_subnets)  # Create one subnet per CIDR

  vpc_id     = aws_vpc.main.id                 # Attach to our VPC
  cidr_block = var.public_subnets[count.index] # Get each CIDR from list
  availability_zone = data.aws_availability_zones.available.names[count.index]
  
  map_public_ip_on_launch = true  # Instances get public IPs

  tags = {
    Name = "${var.project_name}-public-${count.index}"
  }
}

# Create private subnets
resource "aws_subnet" "private" {
  count = length(var.private_subnets)  # Create one subnet per CIDR

  vpc_id     = aws_vpc.main.id                  # Attach to VPC
  cidr_block = var.private_subnets[count.index] # Loop through private subnets
  availability_zone = data.aws_availability_zones.available.names[count.index]

  map_public_ip_on_launch = false  # No public IPs (important!)

  tags = {
    Name = "${var.project_name}-private-${count.index}"
  }
}

# Create Internet Gateway
resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id  # Attach to our VPC

  tags = {
    Name = "${var.project_name}-igw"
  }
}

# Create route table for public subnets
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id  # Attach to VPC

  # Route all internet traffic (0.0.0.0/0) to Internet Gateway
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }

  tags = {
    Name = "${var.project_name}-public-rt"
  }
}

# Associate public subnets with the public route table
resource "aws_route_table_association" "public" {
  count = length(var.public_subnets)  # One association per subnet

  subnet_id      = aws_subnet.public[count.index].id  # Each public subnet
  route_table_id = aws_route_table.public.id          # Attach to public route table
}

# Create Elastic IP (required for NAT Gateway)
resource "aws_eip" "nat" {
  domain = "vpc"  # Allocate EIP for VPC usage

  tags = {
    Name = "${var.project_name}-nat-eip"
  }
}

# Create NAT Gateway in public subnet
resource "aws_nat_gateway" "nat" {
  allocation_id = aws_eip.nat.id            # Attach Elastic IP
  subnet_id     = aws_subnet.public[0].id   # Place NAT in a public subnet

  tags = {
    Name = "${var.project_name}-nat"
  }
}

# Create route table for private subnets
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id  # Attach to VPC

  # Route internet traffic to NAT Gateway
  route {
    cidr_block     = "0.0.0.0/0"         # All internet traffic
    nat_gateway_id = aws_nat_gateway.nat.id
  }

  tags = {
    Name = "${var.project_name}-private-rt"
  }
}

# Associate private subnets with private route table
resource "aws_route_table_association" "private" {
  count = length(var.private_subnets)  # One per private subnet

  subnet_id      = aws_subnet.private[count.index].id  # Each private subnet
  route_table_id = aws_route_table.private.id          # Attach to private route table
}

# IAM role for EKS cluster
resource "aws_iam_role" "eks_cluster_role" {
  name = "${var.project_name}-eks-cluster-role"

  # Trust policy (who can assume this role)
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "eks.amazonaws.com"  # Allow EKS service
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

# Attach required policy to the role
resource "aws_iam_role_policy_attachment" "eks_cluster_policy" {
  role       = aws_iam_role.eks_cluster_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

# Create EKS Cluster
resource "aws_eks_cluster" "main" {
  name     = "${var.project_name}-eks"         # Cluster name
  role_arn = aws_iam_role.eks_cluster_role.arn # IAM role we created

  # Define networking for the cluster
  vpc_config {
    subnet_ids = aws_subnet.private[*].id  # Use private subnets (important)
  }

  # Ensure IAM role is ready before creating cluster
  depends_on = [
    aws_iam_role_policy_attachment.eks_cluster_policy
  ]
}

# IAM role for EKS worker nodes
resource "aws_iam_role" "eks_node_role" {
  name = "${var.project_name}-eks-node-role"

  # Trust policy (EC2 instances will assume this role)
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"  # Allow EC2 to use this role
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

# Attach required policies for worker nodes

# Allows nodes to join EKS cluster
resource "aws_iam_role_policy_attachment" "node_policy_1" {
  role       = aws_iam_role.eks_node_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
}

# Allows networking (CNI plugin)
resource "aws_iam_role_policy_attachment" "node_policy_2" {
  role       = aws_iam_role.eks_node_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
}

# Allows pulling images from ECR
resource "aws_iam_role_policy_attachment" "node_policy_3" {
  role       = aws_iam_role.eks_node_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

# Create EKS Node Group (worker nodes)
resource "aws_eks_node_group" "main" {
  cluster_name    = aws_eks_cluster.main.name   # Attach to EKS cluster
  node_group_name = "${var.project_name}-nodes"
  node_role_arn   = aws_iam_role.eks_node_role.arn

  subnet_ids = aws_subnet.private[*].id  # Use private subnets

  scaling_config {
    desired_size = 2  # Number of nodes to run
    max_size     = 3
    min_size     = 1
  }

  instance_types = ["t3.medium"]  # Instance type for nodes

  depends_on = [
    aws_iam_role_policy_attachment.node_policy_1,
    aws_iam_role_policy_attachment.node_policy_2,
    aws_iam_role_policy_attachment.node_policy_3
  ]
}