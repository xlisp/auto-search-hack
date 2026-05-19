# GET http://127.0.0.1:5050/health

*Token label:* `admin_jwt`  *Response code:* `200`

## Schema sketch

```
{status: string}
```

## Sample response (truncated)

```json
{"status":"ok"}


```

## Reproduce — curl

```bash
TOKEN="$(cat state/tokens/admin.txt)"
curl -H "Authorization: Bearer $TOKEN" 'http://127.0.0.1:5050/health'
```

## Reproduce — python

```python
import requests
token = open("state/tokens/admin.txt").read().strip()
r = requests.get('http://127.0.0.1:5050/health', headers={'Authorization': f'Bearer {token}'})
print(r.status_code)
print(r.json())
```
