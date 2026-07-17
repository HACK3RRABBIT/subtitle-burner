import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import config as appconfig
from subburn.engines.registry import get_asr_engine
from subburn.web.auth import require_auth

router = APIRouter(prefix="/api/settings", dependencies=[Depends(require_auth)])


class SettingsUpdate(BaseModel):
    hf_token: Optional[str] = None
    default_model: Optional[str] = None
    default_lang: Optional[str] = None
    default_source_lang: Optional[str] = None
    force_cpu: Optional[bool] = None
    port: Optional[int] = None
    app_password: Optional[str] = None


@router.get("")
async def get_settings():
    cfg = appconfig.load()
    return {
        "hf_token_set": bool(cfg.get("hf_token")),
        "default_model": cfg.get("default_model"),
        "default_lang": cfg.get("default_lang"),
        "default_source_lang": cfg.get("default_source_lang"),
        "force_cpu": cfg.get("force_cpu"),
        "port": cfg.get("port"),
        "app_password_set": bool(cfg.get("app_password")),
    }


@router.post("")
async def update_settings(body: SettingsUpdate):
    updates = {}
    if body.hf_token is not None and body.hf_token.strip():
        updates["hf_token"] = body.hf_token.strip()
        os.environ["HF_TOKEN"] = updates["hf_token"]
    if body.default_model is not None:
        valid_model_sizes = set(get_asr_engine().list_available_models())
        if body.default_model not in valid_model_sizes:
            raise HTTPException(400, f"Invalid model_size. Must be one of {sorted(valid_model_sizes)}")
        updates["default_model"] = body.default_model
    if body.default_lang is not None:
        updates["default_lang"] = body.default_lang
    if body.default_source_lang is not None:
        updates["default_source_lang"] = body.default_source_lang
    if body.force_cpu is not None:
        updates["force_cpu"] = body.force_cpu
    if body.port is not None:
        updates["port"] = body.port
    if body.app_password is not None:
        # Empty string intentionally disables the password (matches how an
        # empty string already means "auth disabled" everywhere else here).
        updates["app_password"] = body.app_password.strip()

    cfg = appconfig.save(updates)
    return {
        "hf_token_set": bool(cfg.get("hf_token")),
        "default_model": cfg.get("default_model"),
        "default_lang": cfg.get("default_lang"),
        "default_source_lang": cfg.get("default_source_lang"),
        "force_cpu": cfg.get("force_cpu"),
        "port": cfg.get("port"),
        "app_password_set": bool(cfg.get("app_password")),
        "note": "Port changes take effect after restarting the app.",
    }
