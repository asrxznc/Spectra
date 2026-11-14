param(
  [Parameter(Mandatory = $true)]
  [string]$ProjectId,
  [string]$Region = "us-central1",
  [string]$ArtifactRepository = "spectra",
  [string]$WebService = "spectra-web",
  [string]$InferenceService = "spectra-inference"
)

$ErrorActionPreference = "Stop"

gcloud config set project $ProjectId
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com

gcloud artifacts repositories describe $ArtifactRepository `
  --location=$Region *> $null
if ($LASTEXITCODE -ne 0) {
  gcloud artifacts repositories create $ArtifactRepository `
    --repository-format=docker `
    --location=$Region `
    --description="SPECTRA container images"
}

$ImageBase = "$Region-docker.pkg.dev/$ProjectId/$ArtifactRepository"
$InferenceImage = "$ImageBase/$InferenceService"
$WebImage = "$ImageBase/$WebService"

gcloud builds submit `
  --project=$ProjectId `
  --tag=$InferenceImage `
  --file=Dockerfile .
if ($LASTEXITCODE -ne 0) { throw "Inference image build failed." }

gcloud run deploy $InferenceService `
  --project=$ProjectId `
  --region=$Region `
  --image=$InferenceImage `
  --platform=managed `
  --port=8080 `
  --cpu=2 `
  --memory=8Gi `
  --min-instances=0 `
  --max-instances=2 `
  --no-allow-unauthenticated
if ($LASTEXITCODE -ne 0) { throw "Inference service deployment failed." }

$InferenceUrl = gcloud run services describe $InferenceService `
  --project=$ProjectId `
  --region=$Region `
  --format="value(status.url)"
if (-not $InferenceUrl) { throw "Could not resolve the inference service URL." }

gcloud run services add-iam-policy-binding $InferenceService `
  --project=$ProjectId `
  --region=$Region `
  --member="allUsers" `
  --role="roles/run.invoker"
if ($LASTEXITCODE -ne 0) { throw "Could not configure inference invoker access." }

gcloud builds submit `
  --project=$ProjectId `
  --tag=$WebImage `
  --file=Dockerfile.web .
if ($LASTEXITCODE -ne 0) { throw "Web image build failed." }

gcloud run deploy $WebService `
  --project=$ProjectId `
  --region=$Region `
  --image=$WebImage `
  --platform=managed `
  --port=8080 `
  --cpu=1 `
  --memory=1Gi `
  --min-instances=0 `
  --max-instances=3 `
  --set-env-vars="PYTHON_BACKEND_URL=$InferenceUrl" `
  --allow-unauthenticated
if ($LASTEXITCODE -ne 0) { throw "Web service deployment failed." }

Write-Output ""
Write-Output "SPECTRA deployed:"
gcloud run services describe $WebService `
  --project=$ProjectId `
  --region=$Region `
  --format="value(status.url)"
