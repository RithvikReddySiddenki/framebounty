// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {IERC20Metadata} from "@openzeppelin/contracts/token/ERC20/extensions/IERC20Metadata.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @notice Fixed-recipient, fixed-reward escrow with trusted human quality review.
/// @dev All accounting uses ERC-20 atomic units (6 decimals), never msg.value or
/// native gas units. Review timeout releases funds, not automatic acceptance.
contract FrameBountyEscrow is ReentrancyGuard {
    using SafeERC20 for IERC20;

    enum State { None, Reserved, Submitted, Paid, Rejected, Expired, TimedOut }

    struct Job {
        address buyer;
        address reviewer;
        address allocator;
        bytes32 rubric;
        uint64 reviewSeconds;
        bool closed;
        uint256 deposited;
        uint256 committed;
        uint256 paid;
        uint256 refunded;
    }

    struct Reservation {
        bytes32 jobId;
        address recipient;
        uint256 reward;
        uint64 expiresAt;
        uint64 reviewDeadline;
        bytes32 submissionHash;
        State state;
    }

    IERC20 public immutable token;
    mapping(bytes32 => Job) public jobs;
    mapping(bytes32 => Reservation) public reservations;
    mapping(bytes32 => mapping(bytes32 => bool)) public usedRefunds;

    error Unauthorized();
    error InvalidState();
    error InvalidTerms();
    error InsufficientFunds();
    error UnsupportedToken();

    event JobCreated(bytes32 indexed jobId, address indexed buyer, address reviewer, address allocator, bytes32 rubric, uint64 reviewSeconds);
    event Deposited(bytes32 indexed jobId, uint256 amount);
    event Reserved(bytes32 indexed jobId, bytes32 indexed reservationId, address indexed recipient, uint256 reward, uint64 expiresAt);
    event Submitted(bytes32 indexed jobId, bytes32 indexed reservationId, bytes32 submissionHash, uint64 reviewDeadline);
    event Paid(bytes32 indexed jobId, bytes32 indexed reservationId, address indexed recipient, uint256 reward);
    event Released(bytes32 indexed jobId, bytes32 indexed reservationId, State terminalState, bytes32 reasonHash, uint256 reward);
    event Closed(bytes32 indexed jobId);
    event Refunded(bytes32 indexed jobId, bytes32 indexed refundId, address indexed buyer, uint256 amount);

    constructor(address tokenAddress) {
        // No mainnet execution. Standard local tests use 31337; Arc uses its
        // canonical interface, preventing accidental deployment against another token.
        if (block.chainid != 31337 && block.chainid != 5042002) revert InvalidTerms();
        if (block.chainid == 5042002 && tokenAddress != address(0x3600000000000000000000000000000000000000)) revert UnsupportedToken();
        if (tokenAddress.code.length == 0 || IERC20Metadata(tokenAddress).decimals() != 6) revert UnsupportedToken();
        token = IERC20(tokenAddress);
    }

    function createJob(bytes32 id, address reviewer, address allocator, bytes32 rubric, uint64 reviewSeconds) external {
        if (id == bytes32(0) || jobs[id].buyer != address(0) || reviewer == address(0) || allocator == address(0)
            || rubric == bytes32(0) || reviewSeconds < 1 hours || reviewSeconds > 7 days) revert InvalidTerms();
        Job storage job = jobs[id];
        job.buyer = msg.sender;
        job.reviewer = reviewer;
        job.allocator = allocator;
        job.rubric = rubric;
        job.reviewSeconds = reviewSeconds;
        emit JobCreated(id, msg.sender, reviewer, allocator, rubric, reviewSeconds);
    }

    function available(bytes32 jobId) public view returns (uint256) {
        Job storage job = jobs[jobId];
        return job.deposited - job.committed - job.paid - job.refunded;
    }

    function deposit(bytes32 jobId, uint256 amount) external nonReentrant {
        Job storage job = jobs[jobId];
        if (msg.sender != job.buyer) revert Unauthorized();
        if (job.closed || amount == 0) revert InvalidTerms();
        // A job represents one buyer-confirmed fixed budget. A lost wallet/RPC
        // response must not make a retry debit that budget for a second time.
        if (job.deposited != 0) revert InvalidState();
        uint256 beforeBalance = token.balanceOf(address(this));
        token.safeTransferFrom(msg.sender, address(this), amount);
        if (token.balanceOf(address(this)) - beforeBalance != amount) revert UnsupportedToken();
        job.deposited += amount;
        emit Deposited(jobId, amount);
    }

    function reserve(bytes32 jobId, bytes32 id, address recipient, uint256 reward, uint64 expiresAt) external {
        Job storage job = jobs[jobId];
        if (msg.sender != job.allocator && msg.sender != job.buyer) revert Unauthorized();
        if (job.closed || id == bytes32(0) || reservations[id].state != State.None || recipient == address(0)
            || reward == 0 || expiresAt <= block.timestamp || expiresAt > block.timestamp + 7 days) revert InvalidTerms();
        if (reward > available(jobId)) revert InsufficientFunds();
        job.committed += reward;
        reservations[id] = Reservation(jobId, recipient, reward, expiresAt, 0, bytes32(0), State.Reserved);
        emit Reserved(jobId, id, recipient, reward, expiresAt);
    }

    function submit(bytes32 id, bytes32 contentHash) external {
        Reservation storage item = reservations[id];
        if (msg.sender != item.recipient) revert Unauthorized();
        if (item.state != State.Reserved || block.timestamp >= item.expiresAt) revert InvalidState();
        if (contentHash == bytes32(0)) revert InvalidTerms();
        item.state = State.Submitted;
        item.submissionHash = contentHash;
        item.reviewDeadline = uint64(block.timestamp + jobs[item.jobId].reviewSeconds);
        emit Submitted(item.jobId, id, contentHash, item.reviewDeadline);
    }

    function approve(bytes32 id) external nonReentrant {
        Reservation storage item = reservations[id];
        Job storage job = jobs[item.jobId];
        if (msg.sender != job.reviewer) revert Unauthorized();
        if (item.state != State.Submitted || block.timestamp >= item.reviewDeadline) revert InvalidState();
        // Effects precede the external token call. A failed transfer reverts both
        // effects and event; no alternate recipient or reward argument exists.
        item.state = State.Paid;
        job.committed -= item.reward;
        job.paid += item.reward;
        token.safeTransfer(item.recipient, item.reward);
        emit Paid(item.jobId, id, item.recipient, item.reward);
    }

    function reject(bytes32 id, bytes32 reasonHash) external {
        Reservation storage item = reservations[id];
        if (msg.sender != jobs[item.jobId].reviewer) revert Unauthorized();
        if (item.state != State.Submitted || block.timestamp >= item.reviewDeadline) revert InvalidState();
        if (reasonHash == bytes32(0)) revert InvalidTerms();
        release(id, item, State.Rejected, reasonHash);
    }

    /// The dedicated verifier/allocator may only reject and free an obligation.
    /// It cannot pay a contributor, change a recipient or move funds out of escrow.
    function rejectVerification(bytes32 id, bytes32 reasonHash) external {
        Reservation storage item = reservations[id];
        if (msg.sender != jobs[item.jobId].allocator) revert Unauthorized();
        if (item.state != State.Submitted || block.timestamp >= item.reviewDeadline) revert InvalidState();
        if (reasonHash == bytes32(0)) revert InvalidTerms();
        release(id, item, State.Rejected, reasonHash);
    }

    event BatchPaid(bytes32 indexed jobId, bytes32 indexed batchId, address indexed reviewer, bytes32 idsHash, uint256 total, uint256 count);
    mapping(bytes32 => bool) public paidBatches;

    /// One reviewer authorization pays an immutable, bounded set atomically.
    /// Any duplicate, expired item or failed transfer reverts the entire batch.
    function approveBatch(bytes32 batchId, bytes32[] calldata ids) external nonReentrant {
        if (batchId == bytes32(0) || paidBatches[batchId] || ids.length == 0 || ids.length > 20) revert InvalidTerms();
        bytes32 jobId = reservations[ids[0]].jobId;
        Job storage job = jobs[jobId];
        if (msg.sender != job.reviewer) revert Unauthorized();
        uint256 total;
        for (uint256 i; i < ids.length; ++i) {
            Reservation storage item = reservations[ids[i]];
            if (item.jobId != jobId || item.state != State.Submitted || block.timestamp >= item.reviewDeadline) revert InvalidState();
            for (uint256 j; j < i; ++j) if (ids[j] == ids[i]) revert InvalidTerms();
            total += item.reward;
        }
        paidBatches[batchId] = true;
        for (uint256 i; i < ids.length; ++i) {
            Reservation storage item = reservations[ids[i]];
            item.state = State.Paid;
            job.committed -= item.reward;
            job.paid += item.reward;
            token.safeTransfer(item.recipient, item.reward);
            emit Paid(jobId, ids[i], item.recipient, item.reward);
        }
        emit BatchPaid(jobId, batchId, msg.sender, keccak256(abi.encode(ids)), total, ids.length);
    }

    function expire(bytes32 id) external {
        Reservation storage item = reservations[id];
        if (item.state != State.Reserved || block.timestamp < item.expiresAt) revert InvalidState();
        release(id, item, State.Expired, bytes32(0));
    }

    function timeout(bytes32 id) external {
        Reservation storage item = reservations[id];
        if (item.state != State.Submitted || block.timestamp < item.reviewDeadline) revert InvalidState();
        release(id, item, State.TimedOut, bytes32(0));
    }

    function release(bytes32 id, Reservation storage item, State terminalState, bytes32 reasonHash) private {
        item.state = terminalState;
        jobs[item.jobId].committed -= item.reward;
        emit Released(item.jobId, id, terminalState, reasonHash, item.reward);
    }

    function close(bytes32 jobId) external {
        Job storage job = jobs[jobId];
        if (msg.sender != job.buyer) revert Unauthorized();
        if (job.closed) revert InvalidState();
        job.closed = true;
        emit Closed(jobId);
    }

    function refund(bytes32 jobId, bytes32 refundId, uint256 amount) external nonReentrant {
        Job storage job = jobs[jobId];
        if (msg.sender != job.buyer) revert Unauthorized();
        if (!job.closed || amount == 0) revert InvalidTerms();
        if (refundId == bytes32(0) || usedRefunds[jobId][refundId]) revert InvalidTerms();
        if (amount > available(jobId)) revert InsufficientFunds();
        job.refunded += amount;
        usedRefunds[jobId][refundId] = true;
        token.safeTransfer(job.buyer, amount);
        emit Refunded(jobId, refundId, job.buyer, amount);
    }
}
