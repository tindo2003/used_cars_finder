# The scrape/notify Fargate tasks only ever make outbound calls (to dealer
# sites, Craigslist, and Supabase) -- never inbound -- so they run in the
# default VPC's public subnets with a public IP and no NAT Gateway. A NAT
# Gateway would cost real money for zero benefit here: nothing needs to
# reach these tasks from outside.

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_security_group" "scraper_tasks" {
  name        = "${var.project_name}-scraper-tasks"
  description = "Egress-only SG for the scrape/notify Fargate tasks -- no inbound listener of any kind"
  vpc_id      = data.aws_vpc.default.id

  egress {
    description = "All outbound (dealer sites, Craigslist, Supabase, ECR, Secrets Manager, CloudWatch Logs)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Project = var.project_name
  }
}
