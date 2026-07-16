# Sets Resend-related variables on the Railway backend service.
# Prerequisites:
#   1. npx @railway/cli login
#   2. npx @railway/cli link   (inside guayabita-backend)
#   3. Replace placeholder values below

$ErrorActionPreference = "Stop"

$vars = @{
    RESEND_API_KEY = "re_REPLACE_WITH_YOUR_KEY"
    EMAIL_FROM = "Guayabita <noreply@YOUR_DOMAIN.com>"
    FRONTEND_URL = "https://YOUR_APP.vercel.app"
    EMAIL_VERIFY_TOKEN_TTL_HOURS = "48"
    PASSWORD_RESET_TOKEN_TTL_MINUTES = "30"
}

Write-Host "Setting Railway variables for email..."
foreach ($name in $vars.Keys) {
    $value = $vars[$name]
    npx @railway/cli variables set "$name=$value"
}

Write-Host "Done. Redeploy the backend service for changes to take effect."
