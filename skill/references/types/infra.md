# Type: infra

A repository of infrastructure as code: Terraform/OpenTofu, CDK, CloudFormation/SAM, Pulumi, Bicep, Helm, Kubernetes manifests, Ansible. Blueprint: `python <skill-dir>/scripts/new_doc.py --print infra`.

The reader is the platform engineer who will change it, and the application teams who depend on it.

## Reading plan

| Area | Where to look | What to extract |
| --- | --- | --- |
| Resources | Resource blocks/constructs/templates, modules and their inputs | Every resource by logical id/name: type, purpose, environments, consumers |
| Environments | Workspaces, tfvars/var files, stack configs, values files, account/subscription/project mapping, backends/state | Every environment, what differs, where state lives |
| Networking | VPC/VNet, subnets, routes, peering, DNS, ingress/egress, security groups/NSGs, private endpoints | The network picture (diagram when non-trivial) |
| Security | IAM roles/policies, KMS/keys, secrets references (never values), public exposure, encryption settings | Who can do what, what is exposed, how data is protected |
| Observability | Alarms, dashboards, log groups/retention, budgets | What is monitored and who is alerted |
| Workflow | Pipelines (plan/apply, approvals), pre-commit hooks, policy checks (tfsec, checkov, cfn-guard, OPA), drift detection | How a change is reviewed and applied safely |
| Consumers | Outputs, SSM/parameter exports, remote state consumers, application repos the user points to | Who depends on what this repo creates |

## Watch for

- **Never run `apply`, `deploy` or anything that changes state.** `fmt`, `validate`, `lint` and `plan` against non-production environments only with the user's authorisation, because `plan` reads real accounts.
- **Blast radius.** Shared resources (VPCs, DNS zones, IAM boundaries) get a callout: changing them affects other teams.
- **State.** Where it lives, how it is locked, and how to recover it are critical operational knowledge. Write them down.

## Gate notes

Coverage requires:

- IaC resources → `resources-inventory`;
- deployment parameters and environments → `environments`;
- parameter references → `environments` or `security`;
- schedules, pipelines and plaintext-credential files.
