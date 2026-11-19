"""Stateless Exp(1) multipliers, keyed by approved study and replicate.

SHA-256 first 64 bits identify a study. SplitMix64 maps the key, fixed seed
and replicate counter to a 53-bit open uniform, then -log(U) gives Exp(1).
The same study has exactly the same weight in every outcome/model/subset.
This is an implementation change from v1 PCG draws; Monte Carlo limits can
differ slightly although estimands and point estimates are unchanged.
"""
import hashlib
from functools import lru_cache
import numpy as np
@lru_cache(maxsize=2000000)
def study_key(value):return int.from_bytes(hashlib.sha256(str(value).encode()).digest()[:8],'little')
def keys(ids):
 out=np.array([study_key(v) for v in ids],dtype=np.uint64)
 if len(set(map(str,ids)))==len(out) and len(np.unique(out))!=len(out):raise ValueError('Study-key collision')
 return out
def weights_from_keys(k,start,n,seed=20261029):
 with np.errstate(over='ignore'):
  r=np.arange(start+1,start+n+1,dtype=np.uint64)
  x=k[:,None] ^ (r[None,:]*np.uint64(0x9E3779B97F4A7C15)) ^ np.uint64(seed)
  x=x+np.uint64(0x9E3779B97F4A7C15);x=(x^(x>>np.uint64(30)))*np.uint64(0xBF58476D1CE4E5B9)
  x=(x^(x>>np.uint64(27)))*np.uint64(0x94D049BB133111EB);x=x^(x>>np.uint64(31))
  uniform=((x>>np.uint64(11)).astype(np.float64)+.5)/9007199254740992.0
 return -np.log(uniform)
