# GET http://127.0.0.1:5050/api/posts/1

*Token label:* `alice_user`  *Response code:* `200`

## Schema sketch

```
{author_id: int, body: string, id: int, title: string}
```

## Sample response (truncated)

```json
{"author_id":1,"body":"hello","id":1,"title":"first post"}


```

## Reproduce — curl

```bash
TOKEN="$(cat state/tokens/alice.txt)"
curl -H "Authorization: Bearer $TOKEN" 'http://127.0.0.1:5050/api/posts/1'
```

## Reproduce — python

```python
import requests
token = open("state/tokens/alice.txt").read().strip()
r = requests.get('http://127.0.0.1:5050/api/posts/1', headers={'Authorization': f'Bearer {token}'})
print(r.status_code)
print(r.json())
```
