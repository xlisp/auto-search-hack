# GET http://127.0.0.1:5050/api/me

*Token label:* `admin_jwt`  *Response code:* `200`

## Schema sketch

```
{user: {exp: int, iat: int, role: string, sub: string}}
```

## Sample response (truncated)

```json
{"user":{"exp":1779213817,"iat":1779210217,"role":"admin","sub":"admin"}}


```

## Reproduce — curl

```bash
TOKEN="$(cat state/tokens/admin.txt)"
curl -H "Authorization: Bearer $TOKEN" 'http://127.0.0.1:5050/api/me'
```

## Reproduce — python

```python
import requests
token = open("state/tokens/admin.txt").read().strip()
r = requests.get('http://127.0.0.1:5050/api/me', headers={'Authorization': f'Bearer {token}'})
print(r.status_code)
print(r.json())
```
