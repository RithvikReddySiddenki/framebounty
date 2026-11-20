"""Archive visible demo history without erasing any financial evidence or media.

Payment/verification workers retain the same rows, nonce ledger and private bytes.
Only discovery/dashboard history is hidden. All browser sessions are revoked.
"""
from sqlalchemy import select, delete
from .models import Job, AgentSession, AuthSession, Nonce, Audit
from .marketplace import new_id

def archive(db):
    jobs = db.scalars(select(Job).where(Job.archived.is_(False)).with_for_update()).all()
    chats = db.scalars(select(AgentSession).where(AgentSession.profile["archived"].as_boolean().is_distinct_from(True)).with_for_update()).all()
    for job in jobs: job.archived = True
    for chat in chats: chat.profile = {**chat.profile, "archived": True}
    revoked = db.execute(delete(AuthSession)).rowcount
    db.execute(delete(Nonce))
    result = {"archived_posts": len(jobs), "archived_conversations": len(chats), "revoked_sessions": revoked}
    db.add(Audit(id=new_id(), wallet="0x" + "0" * 40, role="operator", action="archive_demo", resource_id="demo", details=result))
    db.commit()
    return result
