from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models_db import RechargePackage, User
from app.dependencies import get_current_admin, get_current_user
from app.models import (
    RechargePackageCreateRequest,
    RechargePackagePublicResponse,
    RechargePackageResponse,
    RechargePackageUpdateRequest,
)
from app.services import package_service

router = APIRouter(tags=["packages"])


def _to_response(package: RechargePackage) -> RechargePackageResponse:
    updated_by_username = package.updated_by.username if package.updated_by else None
    return RechargePackageResponse(
        id=package.id,
        name=package.name,
        price=package.price,
        guayabits=package.guayabits,
        status=package.status,
        popular=package.popular,
        created_at=package.created_at,
        updated_at=package.updated_at,
        updated_by_id=package.updated_by_id,
        updated_by_username=updated_by_username,
    )


@router.get("/packages", response_model=list[RechargePackagePublicResponse])
def list_public_packages(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = current_user
    packages = package_service.list_active_packages(db)
    return [RechargePackagePublicResponse.model_validate(p) for p in packages]


@router.get("/admin/packages", response_model=list[RechargePackageResponse])
def list_admin_packages(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    packages = package_service.list_all_packages(db)
    return [_to_response(p) for p in packages]


@router.get("/admin/packages/{package_id}", response_model=RechargePackageResponse)
def get_admin_package(
    package_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    package = package_service.get_package(db, package_id)
    return _to_response(package)


@router.post("/admin/packages", response_model=RechargePackageResponse, status_code=201)
def create_package(
    payload: RechargePackageCreateRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    package = package_service.create_package(db, payload, admin.id)
    return _to_response(package)


@router.put("/admin/packages/{package_id}", response_model=RechargePackageResponse)
def update_package(
    package_id: int,
    payload: RechargePackageUpdateRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    package = package_service.update_package(db, package_id, payload, admin.id)
    return _to_response(package)
