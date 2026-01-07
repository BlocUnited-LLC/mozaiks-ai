# Deploy Docs (Azure Static Web Apps)

This repo deploys docs to **Azure Static Web Apps** via GitHub Actions.

## How updates work

1. Edit files under `opensoourcedocs/`
2. Commit + push to `main`
3. GitHub Actions builds the MkDocs site and uploads it to Azure

## One-time setup (already done for Mozaiks)

- Azure Static Web App created
- Custom domain `docs.mozaiks.ai` bound in Azure
- GitHub Actions secret set: `AZURE_STATIC_WEB_APPS_API_TOKEN`

## Troubleshooting

- If deployments fail due to auth, re-create/rotate the SWA token and update the GitHub secret.
- If the custom domain breaks, confirm the CNAME for `docs.mozaiks.ai` still points at the SWA hostname.
