# Escrow transition contract (design, not deployed)

All amounts use the USDC ERC-20 interface's integer atomic units. The buyer funds a job;
an authorized allocator may reserve only available funds. The reviewer is fixed per job.
Reservation IDs are globally unique and cannot be reused. Recipient, reward, rubric hash,
job, submission deadline and review duration are immutable after reservation.

| Current | Action and authority | Guard | Result | Accounting |
| --- | --- | --- | --- | --- |
| None | reserve, allocator | job open, funded, positive reward, future deadline | Reserved | available -> committed |
| Reserved | submit, recipient | timestamp < deadline; content hash nonzero | Submitted | unchanged; review deadline starts |
| Reserved | expire, anyone | timestamp >= deadline | Expired (terminal) | committed -> available |
| Submitted | approve/pay, reviewer | timestamp < review deadline | Paid (terminal) | committed -> paid; recipient fixed |
| Submitted | reject, reviewer | timestamp < review deadline; reason hash nonzero | Rejected (terminal) | committed -> available |
| Submitted | timeout, anyone | timestamp >= review deadline | TimedOut (terminal) | committed -> available |
| Open job | close, buyer | authorized buyer | Closed | existing obligations survive |
| Any job | refund, buyer | closed; amount <= available | same | available -> refunded |

Boundary timestamps partition actions without overlap. Approval, rejection and timeout are
mutually exclusive terminal transitions. A submitted reservation cannot be expired using
its original upload deadline. Closing prevents new allocations but allows existing recipients
to submit and receive payment. No on-chain iteration over reservations is needed.

The human reviewer can reject work or abandon review. Timeout releases funds to the job,
and does **not** guarantee contributor payment or fair review. Show this term before confirmation.
The initial proposed review duration is 72 hours and must be buyer-confirmed in the plan.

Conservation: deposited = available + committed + paid + refunded. Token balance is shared
across jobs; sum(available + committed) must be backed. Reject fee-on-transfer tokens.
Use checks-effects-interactions and a reentrancy guard; failed transfers revert the state change.

Off-chain transaction states: intent -> broadcast -> confirmed or reverted. Unknown broadcast
outcomes stay pending and reconcile by reservation events before any retry. Only a verified
successful receipt/event can set paid. The database is a reconstructible chain projection.
