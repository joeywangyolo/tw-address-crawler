"""
API 請求和回應的資料模型定義
使用 Pydantic 進行資料驗證
"""
from typing import Optional, List, Dict
from pydantic import BaseModel, Field, field_validator, ConfigDict
from datetime import datetime


# ============================================================
# 請求模型
# ============================================================

class BatchQueryRequest(BaseModel):
    """批量查詢請求"""
    city_code: str = Field(
        default="63000000",
        description="縣市代碼，預設為台北市 (63000000)"
    )
    start_date: str = Field(
        ...,
        description="起始日期，格式: 114-09-01 (民國年)",
        examples=["114-09-01"]
    )
    end_date: str = Field(
        ...,
        description="結束日期，格式: 114-11-30 (民國年)",
        examples=["114-11-30"]
    )
    register_kind: str = Field(
        default="1",
        description="編釘類別: 1=門牌初編, 2=門牌改編, 3=門牌廢止, 4=門牌復用"
    )
    districts: Optional[List[str]] = Field(
        default=None,
        description="指定行政區列表，為 null 時查詢全部行政區",
        examples=[["松山區", "信義區", "大安區"]]
    )
    save_to_db: bool = Field(
        default=True,
        description="是否將結果存入資料庫"
    )

    @field_validator('districts')
    @classmethod
    def validate_districts(cls, v):
        """驗證行政區名稱"""
        if v is None:
            return v
        
        valid_districts = [
            "松山區", "信義區", "大安區", "中山區", "中正區",
            "大同區", "萬華區", "文山區", "南港區", "內湖區",
            "士林區", "北投區"
        ]
        
        invalid = [d for d in v if d not in valid_districts]
        if invalid:
            raise ValueError(f"無效的行政區: {invalid}，有效值為: {valid_districts}")
        return v
    
    model_config = ConfigDict(
        extra="forbid",  # 禁止未知欄位
        json_schema_extra={
            "example": {
                "city_code": "63000000",
                "start_date": "114-09-01",
                "end_date": "114-11-30",
                "register_kind": "1",
                "districts": ["松山區", "信義區"],
                "save_to_db": True
            }
        }
    )


class DistrictQueryRequest(BaseModel):
    """單一行政區查詢請求"""
    city_code: str = Field(
        default="63000000",
        description="縣市代碼"
    )
    district_name: str = Field(
        ...,
        description="行政區名稱",
        examples=["松山區"]
    )
    start_date: str = Field(
        ...,
        description="起始日期，格式: 114-09-01"
    )
    end_date: str = Field(
        ...,
        description="結束日期，格式: 114-11-30"
    )
    register_kind: str = Field(
        default="1",
        description="編釘類別"
    )
    
    @field_validator('district_name')
    @classmethod
    def validate_district_name(cls, v):
        """驗證行政區名稱"""
        valid_districts = [
            "松山區", "信義區", "大安區", "中山區", "中正區",
            "大同區", "萬華區", "文山區", "南港區", "內湖區",
            "士林區", "北投區"
        ]
        if v not in valid_districts:
            raise ValueError(f"無效的行政區: {v}，有效值為: {valid_districts}")
        return v
    
    model_config = ConfigDict(extra="forbid")  # 禁止未知欄位


# ============================================================
# 回應模型
# ============================================================

class HouseholdRecord(BaseModel):
    """門牌資料"""
    address: str = Field(description="門牌地址")
    date: str = Field(description="編釘日期")
    type: str = Field(description="編釘類別")
    district: Optional[str] = Field(default=None, description="行政區")


class BatchQueryResponse(BaseModel):
    """批量查詢回應"""
    success: bool = Field(description="查詢是否成功")
    total_count: int = Field(description="總資料筆數")
    district_results: Dict[str, int] = Field(description="各行政區資料筆數")
    failed_districts: List[str] = Field(default=[], description="查詢失敗的行政區")
    execution_time: float = Field(description="執行時間 (秒)")
    data: Optional[List[HouseholdRecord]] = Field(
        default=None,
        description="查詢資料 (可選，大量資料時可能不返回)"
    )
    error_message: Optional[str] = Field(default=None, description="錯誤訊息")


class DistrictQueryResponse(BaseModel):
    """單一行政區查詢回應"""
    success: bool
    district_name: str
    total_count: int
    data: List[HouseholdRecord]
    execution_time: float
    error_message: Optional[str] = None


class HealthResponse(BaseModel):
    """健康檢查回應"""
    status: str
    database: str
    version: str
    timestamp: datetime


class ErrorResponse(BaseModel):
    """錯誤回應"""
    success: bool = False
    error_code: str
    error_message: str
    detail: Optional[str] = None
