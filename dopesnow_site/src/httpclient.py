import time, threading
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from urllib.parse import urlparse
from urllib import robotparser
from config import Settings


class RateLimiter:
    def __init__(self, delay:float):
        self.delay=delay
        self._lock=threading.Lock()
        self._last=0.0
    def wait(self):
        with self._lock:
            now=time.time()
            sleep=max(0.0, self._last+self.delay-now)
            if sleep>0: time.sleep(sleep)
            self._last=time.time()
    
class Robots:
    def __init__(self, base_url:str,user_agent:str):
        self.robotparser=robotparser.RobotFileParser()
        if not base_url.endswith("/"):
            base_url+="/"
        robots_url=base_url.rstrip("/")+"robots.txt"
        try:
            self.robotparser.set_url(robots_url)
            self.robotparser.read()
        except Exception:
            pass
        self.user_agent=user_agent
    
    def allowed(self, url:str)->bool:
        try:
            return self.robotparser.can_fetch(self.user_agent, url)
        except Exception:
            return False
    
class HttpClient:
    def __init__(self, settings:Settings):
        self.session=requests.Session()
        self.session.headers.update({"User-Agent":settings.user_agent})
        self.timeout=settings.timeout
        self.ratelimiter=RateLimiter(settings.delay_seconds)
        self.robots=Robots(settings.base_url, settings.user_agent)
        self.settings=settings

    def same_domain(self, url:str)->bool:
        netloc=urlparse(url).netloc.lower()
        return (netloc.split(":")[0] in self.settings.allowed_domains)
    
    @retry(reraise=True,
           retry=retry_if_exception_type((requests.RequestException,)),
           wait=wait_exponential(multiplier=1, min=1, max=16),
           stop=stop_after_attempt(3)
           )
    
    def get(self, url:str) ->requests.Response:
        # if not self.same_domain(url):
        #     raise requests.RequestException(f"Blocked cross-domain: {url}")
        
        # if not self.robots.allowed(url):
        #     raise requests.RequestException(f"Disallowed by robots.txt: {url}")
        
        self.ratelimiter.wait()
        request = self.session.get(url, timeout=self.timeout)
        request.raise_for_status()
        return request

