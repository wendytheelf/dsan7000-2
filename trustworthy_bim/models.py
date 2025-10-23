from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Optional, Any
from uuid import uuid5, NAMESPACE_URL


# ---------- Retrieved doc (寬鬆) ----------
class RetrievedDoc(BaseModel):
    model_config = ConfigDict(extra="allow")
    doc_id: Optional[str] = None
    title: Optional[str] = None
    source: Optional[str] = None
    path: Optional[str] = None
    score: Optional[float] = None
    rerank: Optional[float] = None
    snippet: Optional[str] = None


# ---------- Entity (符合你貼的樣子) ----------
class Entity(BaseModel):
    model_config = ConfigDict(extra="allow")
    uid: str
    ifc_class: Optional[str] = None
    name: Optional[str] = None
    long_name: Optional[str] = None
    global_id: Optional[str] = None
    attributes: Dict[str, Any] = {}
    properties: Dict[str, Any] = {}
    spatial_path: Optional[List[str]] = None
    tier_label: Optional[str] = None


# ---------- UIR pack (neighbors 是 list) ----------
class NeighborItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    rel: Optional[str] = None
    direction: Optional[str] = None
    class_: Optional[str] = Field(default=None, alias="class")
    name: Optional[str] = None
    uid: Optional[str] = None


class UIRPack(BaseModel):
    model_config = ConfigDict(extra="allow")
    run_id: Optional[str] = None
    entity: Entity
    neighbors: Optional[List[NeighborItem]] = []
    retrieved_docs: Optional[List[RetrievedDoc]] = []


# ---------- Canonical / Output ----------
class CanonicalProperty(BaseModel):
    asset_id: str
    name: str
    value_raw: Any
    unit_raw: Optional[str] = None
    value_norm: Optional[float] = None
    unit_norm: Optional[str] = None
    confidence: Optional[float] = Field(None, ge=0, le=1)


class CanonicalAsset(BaseModel):
    asset_id: str
    source: str
    local_id: str
    canonical_class: Optional[str] = None
    ifc_class: Optional[str] = None
    uniclass_code: Optional[str] = None
    site: Optional[str] = None
    building: Optional[str] = None
    level: Optional[str] = None
    space: Optional[str] = None


class CanonicalRelation(BaseModel):
    asset_id: str
    relation: str   # "partOfSystem" | "connectedTo" | "containedIn" | ...
    target_local_id: str


class FlagRecord(BaseModel):
    asset_id: str
    flag: str       # MISSING_REQUIRED_PROPERTY | OUT_OF_RANGE | LOW_AI_CONF | INCONSISTENT_NEIGHBOR
    reason: Optional[str] = None


# ---------- Helpers ----------
def make_asset_id(source: str, local_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"{source}:{local_id}"))
