# src/config.py

from dataclasses import dataclass, field
from typing import Set

@dataclass
class Settings:
    base_url:str=r"https://www.dopesnow.com/"
    user_agent: str =("Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
    timeout:int=20
    delay_seconds:float=0.01
    max_retries:int=3
    concurrence:int=1
    output_file:str="./data/product.csv"
    allowed_domains: Set[str] = field(default_factory=lambda: {"www.dopesnow.com", "dopesnow.com"})
