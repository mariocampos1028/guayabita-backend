from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.db.database import get_db
from app.db.models_db import SupportMessage, SupportTicket, User
from app.dependencies import get_current_admin, get_current_user
from app.models import (
    SupportMessageCreateRequest,
    SupportTicketCreateRequest,
    SupportTicketResponse,
)

router = APIRouter(tags=["support"])


def _ticket_response(ticket: SupportTicket) -> SupportTicketResponse:
    user = ticket.user
    return SupportTicketResponse(
        id=ticket.id, user_id=ticket.user_id, username=user.username,
        customer_first_name=user.first_name, customer_last_name=user.last_name,
        customer_email=user.email, customer_phone=user.phone, category=ticket.category,
        title=ticket.title, status=ticket.status, created_at=ticket.created_at,
        updated_at=ticket.updated_at, closed_at=ticket.closed_at, messages=ticket.messages,
    )


def _get_ticket(db: Session, ticket_id: int) -> SupportTicket:
    ticket = db.query(SupportTicket).options(
        joinedload(SupportTicket.user), joinedload(SupportTicket.messages)
    ).filter(SupportTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    return ticket


@router.post("/support/tickets", response_model=SupportTicketResponse, status_code=201)
def create_ticket(payload: SupportTicketCreateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ticket = SupportTicket(user_id=user.id, category=payload.category, title=payload.title.strip())
    db.add(ticket)
    db.flush()
    db.add(SupportMessage(ticket_id=ticket.id, sender_id=user.id, sender_role="user", content=payload.detail.strip()))
    db.commit()
    return _ticket_response(_get_ticket(db, ticket.id))


@router.get("/support/tickets/me", response_model=list[SupportTicketResponse])
def my_tickets(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    tickets = db.query(SupportTicket).options(joinedload(SupportTicket.user), joinedload(SupportTicket.messages)).filter(
        SupportTicket.user_id == user.id
    ).order_by(SupportTicket.updated_at.desc()).all()
    return [_ticket_response(ticket) for ticket in tickets]


@router.post("/support/tickets/{ticket_id}/messages", response_model=SupportTicketResponse)
def reply_ticket(ticket_id: int, payload: SupportMessageCreateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ticket = _get_ticket(db, ticket_id)
    if ticket.user_id != user.id:
        raise HTTPException(status_code=403, detail="No tienes acceso a esta solicitud")
    if ticket.status != "open":
        raise HTTPException(status_code=409, detail="La solicitud está cerrada; reábrela para responder")
    db.add(SupportMessage(ticket_id=ticket.id, sender_id=user.id, sender_role="user", content=payload.content.strip()))
    ticket.updated_at = datetime.now(timezone.utc)
    db.commit()
    return _ticket_response(_get_ticket(db, ticket.id))


@router.post("/support/tickets/{ticket_id}/reopen", response_model=SupportTicketResponse)
def reopen_ticket(ticket_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ticket = _get_ticket(db, ticket_id)
    if ticket.user_id != user.id:
        raise HTTPException(status_code=403, detail="No tienes acceso a esta solicitud")
    ticket.status, ticket.closed_at, ticket.updated_at = "open", None, datetime.now(timezone.utc)
    db.commit()
    return _ticket_response(_get_ticket(db, ticket.id))


@router.get("/admin/support/tickets", response_model=list[SupportTicketResponse])
def admin_tickets(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    _ = admin
    tickets = db.query(SupportTicket).options(joinedload(SupportTicket.user), joinedload(SupportTicket.messages)).order_by(SupportTicket.updated_at.desc()).all()
    return [_ticket_response(ticket) for ticket in tickets]


@router.get("/admin/support/open-count")
def open_count(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    _ = admin
    return {"count": db.query(SupportTicket).filter(SupportTicket.status == "open").count()}


@router.post("/admin/support/tickets/{ticket_id}/messages", response_model=SupportTicketResponse)
def admin_reply(ticket_id: int, payload: SupportMessageCreateRequest, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    ticket = _get_ticket(db, ticket_id)
    if ticket.status != "open":
        raise HTTPException(status_code=409, detail="La solicitud está cerrada")
    db.add(SupportMessage(ticket_id=ticket.id, sender_id=admin.id, sender_role="admin", content=payload.content.strip()))
    ticket.updated_at = datetime.now(timezone.utc)
    db.commit()
    return _ticket_response(_get_ticket(db, ticket.id))


@router.post("/admin/support/tickets/{ticket_id}/close", response_model=SupportTicketResponse)
def close_ticket(ticket_id: int, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    _ = admin
    ticket = _get_ticket(db, ticket_id)
    ticket.status, ticket.closed_at, ticket.updated_at = "closed", datetime.now(timezone.utc), datetime.now(timezone.utc)
    db.commit()
    return _ticket_response(_get_ticket(db, ticket.id))
