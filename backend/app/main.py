"""FastAPI interface — the thin demo layer over the adjudication engine.

Endpoints exercise the whole system end-to-end:
  POST /claims                      submit a claim with line items and adjudicate it
  GET  /claims/{id}                 retrieve a persisted, adjudicated claim
  POST /claims/{id}/disputes        open a dispute on a line of a claim
  POST /disputes/{id}/resolve       resolve a dispute -> re-adjudicate the line
"""
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException

from app import claims_service as svc
from app.claims_repository import ClaimRepository, SupabaseClaimRepository
from app.db import get_supabase
from app.schemas import ClaimIn, ClaimOut, DisputeIn, DisputeOut

app = FastAPI(title="Claims Processing System", version="1.0.0")


def get_repository() -> ClaimRepository:
    """Inject the live repository; overridden with a fake in tests."""
    return SupabaseClaimRepository(get_supabase())


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/claims", response_model=ClaimOut, status_code=201)
def submit_claim(payload: ClaimIn, repo: ClaimRepository = Depends(get_repository)):
    try:
        return svc.submit_claim(repo, payload)
    except svc.PolicyNotFound:
        raise HTTPException(status_code=404, detail="Policy not found.")
    except svc.UnknownServiceType as exc:
        raise HTTPException(status_code=422, detail=f"Unknown service type: {exc.code}")


@app.get("/claims/{claim_id}", response_model=ClaimOut)
def get_claim(claim_id: UUID, repo: ClaimRepository = Depends(get_repository)):
    try:
        return svc.get_claim(repo, str(claim_id))
    except svc.ClaimNotFound:
        raise HTTPException(status_code=404, detail="Claim not found.")


@app.post("/claims/{claim_id}/disputes", response_model=DisputeOut, status_code=201)
def open_dispute(claim_id: UUID, payload: DisputeIn, repo: ClaimRepository = Depends(get_repository)):
    try:
        return svc.open_dispute(repo, str(claim_id), payload)
    except svc.ClaimNotFound:
        raise HTTPException(status_code=404, detail="Claim not found.")
    except svc.LineNotInClaim:
        raise HTTPException(status_code=422, detail="line_item_id does not belong to this claim.")


@app.post("/disputes/{dispute_id}/resolve", response_model=ClaimOut)
def resolve_dispute(dispute_id: UUID, repo: ClaimRepository = Depends(get_repository)):
    try:
        return svc.resolve_dispute(repo, str(dispute_id))
    except svc.DisputeNotFound:
        raise HTTPException(status_code=404, detail="Dispute not found.")
    except svc.DisputeAlreadyResolved:
        raise HTTPException(status_code=409, detail="Dispute is already resolved.")
    except svc.LineNotInClaim:
        raise HTTPException(status_code=422, detail="Dispute is not resolvable (no target line item).")
