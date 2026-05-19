# GET http://127.0.0.1:5050/api/posts

*Token label:* `admin_jwt`  *Response code:* `200`

## Schema sketch

```
{posts: array<{author_id: int, body: string, id: int, title: string}>}
```

## Sample response (truncated)

```json
{"posts":[{"author_id":1,"body":"hello","id":1,"title":"first post"},{"author_id":2,"body":"world","id":2,"title":"second post"}]}


```

## Reproduce — curl

```bash
TOKEN="$(cat state/tokens/admin.txt)"
curl -H "Authorization: Bearer $TOKEN" 'http://127.0.0.1:5050/api/posts'
```

## Reproduce — python

```python
import requests
token = open("state/tokens/admin.txt").read().strip()
r = requests.get('http://127.0.0.1:5050/api/posts', headers={'Authorization': f'Bearer {token}'})
print(r.status_code)
print(r.json())
```
