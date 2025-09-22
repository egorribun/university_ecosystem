import time
from fastapi import HTTPException, status

class MemoryLimiter:
  def __init__(self):
    self.bucket = {}

  def check(self, key: str, limit: int, window_sec: int):
    now = time.time()
    arr = [t for t in self.bucket.get(key, []) if now - t < window_sec]
    if len(arr) >= limit:
      raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Слишком много запросов")
    arr.append(now)
    self.bucket[key] = arr

limiter = MemoryLimiter()