import hashlib
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Document, Organization, User, utcnow
from app.security import hash_password
from app.services.documents import process_document


DEMO_ORGANIZATIONS = [
    ("星海数据科技", "nova-data"),
    ("远峰零售", "apex-retail"),
]

DEMO_USERS = [
    ("alice@nova.test", "林晓", "CUSTOMER", "nova-data", "customer123"),
    ("bob@apex.test", "周远", "CUSTOMER", "apex-retail", "customer123"),
    ("support@flowpilot.test", "陈工", "SUPPORT", None, "support123"),
]


def seed_demo(db: Session) -> None:
    organizations: dict[str, Organization] = {}
    for name, slug in DEMO_ORGANIZATIONS:
        organization = db.scalar(sa.select(Organization).where(Organization.slug == slug))
        if not organization:
            organization = Organization(name=name, slug=slug)
            db.add(organization)
            db.flush()
        organizations[slug] = organization
    users: dict[str, User] = {}
    for email, name, role, org_slug, password in DEMO_USERS:
        user = db.scalar(sa.select(User).where(User.email == email))
        if not user:
            user = User(
                email=email,
                display_name=name,
                role=role,
                organization_id=organizations[org_slug].id if org_slug else None,
                password_hash=hash_password(password),
            )
            db.add(user)
            db.flush()
        users[email] = user
    db.commit()

    support = users["support@flowpilot.test"]
    source_dir = get_settings().demo_knowledge_dir.resolve()
    if not source_dir.exists():
        return
    for path in sorted(source_dir.glob("*.md")):
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if db.scalar(
            sa.select(Document).where(
                sa.or_(
                    Document.sha256 == digest,
                    sa.and_(Document.logical_name == path.stem, Document.version == 1),
                )
            )
        ):
            continue
        document = Document(
            logical_name=path.stem,
            filename=path.name,
            version=1,
            content_type="text/markdown",
            file_path=str(path.resolve()),
            sha256=digest,
            size_bytes=len(content),
            uploaded_by_id=support.id,
        )
        db.add(document)
        db.commit()
        process_document(db, document.id)
        document.status = "PUBLISHED"
        document.published_at = utcnow()
        db.commit()
