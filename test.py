import requests, json

url = 'https://ltceip4prod.azure-api.net/AI/completions'
headers = {
    "Content-Type": "application/json",
    "Ocp-Apim-Subscription-Key": "351588a104744813bf00652d900cb3a0",
    "x-api-key": "eyJ0ZWFtIjogIklQTVMiLCAiZW52IjogInByb2QifQ=="
}
data = {
  "model": "GPT-OSS-120B",
   "messages": [{"role": "user", "content": "hi"}]
}
r = requests.post(url, headers=headers, json=data)
print(r.status_code, r.text)