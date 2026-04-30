from enum import Enum

class HttpStatus(Enum):
    Ok = 200
    NotFound = 404
    ServerError = 500

s = HttpStatus.NotFound
print("ok")
