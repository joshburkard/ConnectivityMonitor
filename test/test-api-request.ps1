$headers = @{
    'Content-Type'= 'application/xml'
    securityToken = '97b3f2c4-5b65-486b-a30d-a5390b82e51c'
}

$URI = 'https://web-api.tp.entsoe.eu/api?documentType=A44&out_Domain=10YBE----------&in_Domain=10YBE----------&periodStart=202412022200&periodEnd=202412032200'

$URI = 'https://web-api.tp.entsoe.eu/api?documentType=A44&periodStart=202407272200&periodEnd=202407282200&out_Domain=10YBE----------2&in_Domain=10YBE----------2&securityToken=97b3f2c4-5b65-486b-a30d-a5390b82e51c'
$URI = 'https://web-api.tp.entsoe.eu/api?documentType=A44&periodStart=202407272200&periodEnd=202407282200&out_Domain=10YBE----------2&in_Domain=10YBE----------2&securityToken=97b3f2c4-5b65-486b-a30d-a5390b82e51c'

$URI = 'https://web-api.tp.entsoe.eu/api?securityToken=97b3f2c4-5b65-486b-a30d-a5390b82e51c&documentType=A44&in_Domain=10YBE----------2&out_Domain=10YBE----------2&periodStart=202412012200&periodEnd=202412022200'
( Invoke-WebRequest -Uri $URI -Method Get ).Content
$response = Invoke-RestMethod -Uri $uri -Method 'GET' -Headers $headers
$response.ToString()
$response.Publication_MarketDocument.TimeSeries
$r = $response | ConvertTo-Json
$r
$response.Publication_MarketDocument.TimeSeries.curveType[0].per