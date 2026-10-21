"""ส่วนที่ 4: FastAPI — coin-types, อัปโหลด, ดูผล, ดูภาพ (ตอนนี้เก็บในหน่วยความจำ)"""

import io
import logging
import uuid
from collections import OrderedDict
from dataclasses import dataclass

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import Response
from PIL import Image, ImageOps, UnidentifiedImageError

from schemas import COIN_TYPES, AnalysisResponse, CoinTypeInfo

from . import pipeline

logging.basicConfig(level=logging.INFO)

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_PIXELS = 50_000_000  # ไฟล์เล็กแต่ความละเอียดสูงมาก (เช่น PNG สีพื้น) ใช้หน่วยความจำมหาศาลตอนถอดรหัส
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_ANALYSES = 20

app = FastAPI(title="baht-counter API")


@dataclass
class Analysis:
    response: AnalysisResponse
    images: dict[str, bytes]  # ชื่อ -> PNG/JPEG bytes


# shortcut: เก็บในหน่วยความจำแค่ MAX_ANALYSES ผลล่าสุด หายเมื่อรีสตาร์ท — เปลี่ยนเป็น SQLite + storage/ (ส่วนที่ 4)
ANALYSES: OrderedDict[str, Analysis] = OrderedDict()


def decode_image(data: bytes) -> np.ndarray:
    """อ่านไฟล์ หมุนตาม EXIF orientation แล้วคืนภาพ BGR"""
    try:
        img = Image.open(io.BytesIO(data))
        if img.width * img.height > MAX_PIXELS:
            raise HTTPException(413, "ภาพมีความละเอียดสูงเกินไป กรุณาใช้ภาพไม่เกิน 50 ล้านพิกเซล")
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Image.DecompressionBombError:
        raise HTTPException(413, "ภาพมีความละเอียดสูงเกินไป กรุณาใช้ภาพไม่เกิน 50 ล้านพิกเซล")
    except (UnidentifiedImageError, OSError):
        raise HTTPException(400, "อ่านไฟล์ภาพไม่ได้ กรุณาใช้ไฟล์ JPEG, PNG หรือ WebP")
    return cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)


def encode_png(img: np.ndarray) -> bytes:
    _, buf = cv2.imencode(".png", img)
    return buf.tobytes()


@app.get("/api/coin-types", response_model=list[CoinTypeInfo])
def coin_types():
    return COIN_TYPES


# def ธรรมดา (ไม่ใช่ async) FastAPI จะรันใน threadpool งานประมวลผลภาพจึงไม่บล็อก request อื่น
@app.post("/api/analyses", response_model=AnalysisResponse)
def create_analysis(file: UploadFile):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, "รองรับเฉพาะไฟล์ JPEG, PNG หรือ WebP")
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "ไฟล์ใหญ่เกิน 15 MB")

    image = decode_image(data)
    result, debug = pipeline.run(image)

    analysis_id = uuid.uuid4().hex
    images = {"original": data, **{name: encode_png(img) for name, img in debug.items()}}
    result = result.model_copy(update={
        "debug_images": {name: f"/api/analyses/{analysis_id}/images/{name}" for name in debug},
    })
    response = AnalysisResponse(analysis_id=analysis_id, result=result)
    ANALYSES[analysis_id] = Analysis(response=response, images=images)
    while len(ANALYSES) > MAX_ANALYSES:
        ANALYSES.popitem(last=False)
    return response


def get_or_404(analysis_id: str) -> Analysis:
    if analysis_id not in ANALYSES:
        raise HTTPException(404, "ไม่พบผลการนับนี้")
    return ANALYSES[analysis_id]


@app.get("/api/analyses/{analysis_id}", response_model=AnalysisResponse)
def get_analysis(analysis_id: str):
    return get_or_404(analysis_id).response


@app.get("/api/analyses/{analysis_id}/images/{name}")
def get_image(analysis_id: str, name: str):
    images = get_or_404(analysis_id).images
    if name not in images:
        raise HTTPException(404, "ไม่พบภาพนี้")
    data = images[name]
    media = Image.open(io.BytesIO(data)).get_format_mimetype() or "application/octet-stream"
    return Response(data, media_type=media)
