import re, json
from bs4 import BeautifulSoup
from typing import Dict, Any, List, Optional

def soupify(html:str)->BeautifulSoup:
    return BeautifulSoup(html,"lxml")

def textnorm(s:str)->str:
    return re.sub(r"\s+", " ", s or "").strip()

def extract_build_id(html:str) -> Optional[str]:
    