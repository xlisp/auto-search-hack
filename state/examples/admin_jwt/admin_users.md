# GET http://127.0.0.1:5050/admin/users

*Token label:* `admin_jwt`  *Response code:* `200`

## Schema sketch

```
{users: array<{id: int, role: string, username: string}>}
```

## Sample response (truncated)

```json
{"users":[{"id":1,"role":"user","username":"alice"},{"id":2,"role":"user","username":"bob"},{"id":99,"role":"admin","username":"admin"}]}


```

## Reproduce — curl

```bash
TOKEN="$(cat state/tokens/admin.txt)"
curl -H "Authorization: Bearer $TOKEN" 'http://127.0.0.1:5050/admin/users'
```

## Reproduce — python

```python
import requests
token = open("state/tokens/admin.txt").read().strip()
r = requests.get('http://127.0.0.1:5050/admin/users', headers={'Authorization': f'Bearer {token}'})
print(r.status_code)
print(r.json())
```
