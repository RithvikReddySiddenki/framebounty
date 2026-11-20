from sqlalchemy import select, func
from sqlalchemy.orm import Session
from framebounty.demo_archive import archive
from framebounty.auth import create_session
from framebounty.models import Job, Reservation, AgentSession, Audit
from test_postgres import pg
from test_submission_flow import flow

def test_archive_clears_visible_workspace_but_preserves_obligations(pg, flow):
    client, buyer, actor, _, jid, rid = flow
    with Session(pg) as db:
        job = db.get(Job, jid)
        owner = job.buyer
        contributor = db.get(Reservation, rid).wallet
        before = (job.deposited_atomic, job.committed_atomic, job.paid_atomic)
        db.add(AgentSession(id="archive-chat", wallet=owner, role="buyer", profile={"chat": True}))
        db.commit()
        result = archive(db)
        assert result["archived_posts"] == 1 and result["archived_conversations"] == 1
        assert db.get(Job, jid).archived
        assert (job.deposited_atomic, job.committed_atomic, job.paid_atomic) == before
        assert db.get(Reservation, rid) is not None
        assert db.scalar(select(func.count()).select_from(Audit)) > 0
        new_buyer = {"Authorization": "Bearer " + create_session(db, owner)}
        new_actor = {"Authorization": "Bearer " + create_session(db, contributor)}
    assert client.get("/me/jobs", headers=buyer).status_code == 401
    assert client.get("/me/jobs", headers=new_buyer).json()["jobs"] == []
    assert client.get("/me/overview", headers=new_buyer).json()["collections"] == 0
    assert client.get("/me/reservations", headers=new_actor).json()["reservations"] == []
    assert client.get("/tasks", headers=new_actor).json()["tasks"] == []
    assert client.get("/chat-sessions?role=buyer", headers=new_buyer).json()["sessions"] == []
    assert client.get("/agent-sessions/archive-chat", headers=new_buyer).status_code == 404
