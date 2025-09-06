from bot_detector.website.api import (
    account_search,
    contact,
    contributors,
    cookies,
    faq,
    home,
    monitoring,
)
from fastapi import APIRouter

router = APIRouter()
router.include_router(monitoring.router)
router.include_router(home.router)
router.include_router(account_search.router)
router.include_router(contributors.router)
router.include_router(contact.router)
router.include_router(faq.router)
router.include_router(cookies.router)
