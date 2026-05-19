# GET http://127.0.0.1:5050/api/posts/2

*Token label:* `alice_user`  *Response code:* `200`

## Schema sketch

```
{author_id: int, body: string, id: int, title: string}
```

## Sample response (truncated)

```json
{"author_id":2,"body":"world","id":2,"title":"second post"}


```

## Reproduce — curl

```bash
TOKEN="$(cat state/tokens/alice.txt)"
curl -H "Authorization: Bearer $TOKEN" 'http://127.0.0.1:5050/api/posts/2'
```

## Reproduce — python

```python
import requests
token = open("state/tokens/alice.txt").read().strip()
r = requests.get('http://127.0.0.1:5050/api/posts/2', headers={'Authorization': f'Bearer {token}'})
print(r.status_code)
print(r.json())
```
