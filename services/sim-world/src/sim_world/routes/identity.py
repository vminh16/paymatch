"""Identity routes: /sim/identity/*."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from sim_world.auth import require_caller
from sim_world.jwt_keys import IdentityKeyStore
from sim_world.schemas import (
    JwksResponse,
    MerchantTokenRequest,
    MerchantTokenResponse,
    StaffTokenRequest,
    StaffTokenResponse,
    StepUpChallengeRequest,
    StepUpChallengeResponse,
    StepUpVerifyRequest,
    StepUpVerifyResponse,
)
from sim_world.store import SimWorldStore

router = APIRouter(
    prefix="/sim/identity",
    tags=["identity"],
    dependencies=[Depends(require_caller("core", "gate", allow_demo_mode=True))],
)


@router.get("/.well-known/jwks.json", response_model=JwksResponse)
def get_jwks(request: Request) -> dict:
    keys: IdentityKeyStore = request.app.state.keys
    return keys.jwks()


@router.post("/merchant-tokens", response_model=MerchantTokenResponse)
def issue_merchant_token(body: MerchantTokenRequest, request: Request) -> dict:
    store: SimWorldStore = request.app.state.store
    return {"momo_token": store.issue_merchant_token(body.user_id)}


@router.post("/staff-tokens", response_model=StaffTokenResponse)
def issue_staff_token(body: StaffTokenRequest, request: Request) -> dict:
    store: SimWorldStore = request.app.state.store
    return {"sso_token": store.issue_staff_token(body.staff_id)}


@router.post("/step-up-challenges", response_model=StepUpChallengeResponse)
def create_step_up_challenge(body: StepUpChallengeRequest, request: Request) -> dict:
    store: SimWorldStore = request.app.state.store
    return store.create_step_up_challenge(body.momo_token, body.action_hash)


@router.post(
    "/step-up-challenges/{challenge_id}:verify",
    response_model=StepUpVerifyResponse,
)
def verify_step_up_challenge(
    challenge_id: str,
    body: StepUpVerifyRequest,
    request: Request,
) -> dict:
    store: SimWorldStore = request.app.state.store
    return {"auth_proof": store.verify_step_up_challenge(challenge_id, body.otp)}
