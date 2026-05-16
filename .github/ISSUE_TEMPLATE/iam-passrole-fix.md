---
name: 'Fix `iam:PassRole` permission for GitHubActions role'
about: 'Address access denied issue in ECS deployment pipeline'
title: 'Fix `iam:PassRole` permission issue'
labels: ['bug', 'priority: high']
---

## Description
The GitHub Actions deployment pipeline encountered an `AccessDeniedException` while attempting to perform the `iam:PassRole` action on the `ecsTaskRole-next-voters-agent`. For deployment workflows using ECS, the required IAM permissions must be added for the role used in the GitHub Action to pass roles successfully.

## Error Details:
```
An error occurred (AccessDeniedException) when calling the RegisterTaskDefinition operation: User: arn:aws:sts::595172359776:assumed-role/GitHubActions-ECR-Push/GitHubActions is not authorized to perform: iam:PassRole on resource: arn:aws:iam::595172359776:role/ecsTaskRole-next-voters-agent because no identity-based policy allows the iam:PassRole action
```

## Steps to Reproduce:
1. Run the GitHub Actions workflow for deploying the ECS task.
2. The workflow fails to progress at the step `aws ecs register-task-definition` due to insufficient permission.

## Suggested Fix:
1. Update the IAM policy for the GitHubActions-ECR-Push role to allow `iam:PassRole` for the ECS task execution role.
   - **Action:** `iam:PassRole`
   - **Resource:** `arn:aws:iam::595172359776:role/ecsTaskRole-next-voters-agent`

### Example of Updated Policy:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::595172359776:role/ecsTaskRole-next-voters-agent"
    }
  ]
}
```

2. Attach this policy to the GitHubActions-ECR-Push role and verify permissions.

3. Re-run the GitHub Actions workflow.

## Additional Notes:
- Ensure you follow the [principle of least privilege](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html) when updating IAM policies.
- If you need urgent help, let me know.

---