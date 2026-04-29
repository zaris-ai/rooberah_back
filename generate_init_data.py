import json
import time
import hmac
import hashlib
from urllib.parse import urlencode

BOT_TOKEN = "8794100819:AAE3l9iicYfSRPeqW0L11d7nWtvTDXHhA2g"

data = {
    "query_id": "test-query-id",
    "user": json.dumps({
        "id": 123456789,
        "first_name": "Test",
        "username": "test_user",
        "language_code": "fa",
    }, separators=(",", ":")),
    "auth_date": str(int(time.time())),
}

data_check_string = "\n".join(
    f"{key}={value}" for key, value in sorted(data.items())
)

secret_key = hmac.new(
    key=b"WebAppData",
    msg=BOT_TOKEN.encode(),
    digestmod=hashlib.sha256,
).digest()

hash_value = hmac.new(
    key=secret_key,
    msg=data_check_string.encode(),
    digestmod=hashlib.sha256,
).hexdigest()

data["hash"] = hash_value

print(urlencode(data))