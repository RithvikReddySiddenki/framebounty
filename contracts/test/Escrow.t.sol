// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {FrameBountyEscrow} from "../src/FrameBountyEscrow.sol";

interface Vm {
    function prank(address) external;
    function warp(uint256) external;
    function expectRevert() external;
    function expectRevert(bytes4) external;
}

contract TestUSDC is ERC20 {
    bool public failTransfer;
    bool public fee;
    address public callbackTarget;
    bytes public callbackData;
    bool public callbackSucceeded;
    constructor() ERC20("Local test USDC", "USDC") {}
    function decimals() public pure override returns (uint8) { return 6; }
    function mint(address to, uint256 amount) external { _mint(to, amount); }
    function setFailure(bool value) external { failTransfer = value; }
    function setFee(bool value) external { fee = value; }
    function setCallback(address target, bytes calldata data) external {
        callbackTarget = target;
        callbackData = data;
    }
    function transfer(address to, uint256 amount) public override returns (bool) {
        if (failTransfer) return false;
        if (callbackTarget != address(0)) {
            address target = callbackTarget;
            callbackTarget = address(0);
            (callbackSucceeded,) = target.call(callbackData);
        }
        return super.transfer(to, amount);
    }
    function _update(address from, address to, uint256 value) internal override {
        if (fee && from != address(0) && to != address(0) && value > 1) {
            super._update(from, to, value - 1);
            super._update(from, address(0), 1);
        } else super._update(from, to, value);
    }
}

/// @dev Runs on a local EVM against an external-boundary test token. Arc's shared
/// native/token balance behavior still needs a separate Arc-specific smoke flow.
contract EscrowTest {
    Vm constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));
    bytes32 constant JOB = keccak256("job");
    bytes32 constant R = keccak256("reservation");
    bytes32 constant REFUND = keccak256("refund-intent");
    address constant BUYER = address(0xB);
    address constant REVIEWER = address(0xA);
    address constant ALLOCATOR = address(0xC);
    address constant CONTRIBUTOR = address(0xD);
    address constant STRANGER = address(0xE);
    TestUSDC token;
    FrameBountyEscrow escrow;

    function setUp() public {
        token = new TestUSDC();
        escrow = new FrameBountyEscrow(address(token));
        token.mint(BUYER, 20_000_000);
        vm.prank(BUYER);
        token.approve(address(escrow), type(uint256).max);
        vm.prank(BUYER);
        escrow.createJob(JOB, REVIEWER, ALLOCATOR, keccak256("rubric-v1"), 72 hours);
        vm.prank(BUYER);
        escrow.deposit(JOB, 20_000_000);
    }

    function reserved(uint256 amount) internal {
        vm.prank(ALLOCATOR);
        escrow.reserve(JOB, R, CONTRIBUTOR, amount, uint64(block.timestamp + 1 hours));
    }

    function submitted(uint256 amount) internal {
        reserved(amount);
        vm.prank(CONTRIBUTOR);
        escrow.submit(R, keccak256("consented-clip"));
    }

    function conservation() internal view {
        (,,,,,, uint256 deposited, uint256 committed, uint256 paid, uint256 refunded) = escrow.jobs(JOB);
        require(deposited == escrow.available(JOB) + committed + paid + refunded, "ledger conservation");
        require(token.balanceOf(address(escrow)) == escrow.available(JOB) + committed, "escrow backing");
    }

    function testUnauthorizedActions() public {
        vm.expectRevert(FrameBountyEscrow.Unauthorized.selector);
        vm.prank(STRANGER);
        escrow.reserve(JOB, R, STRANGER, 1, uint64(block.timestamp + 1));
        submitted(1_000_000);
        vm.expectRevert(FrameBountyEscrow.Unauthorized.selector);
        vm.prank(STRANGER);
        escrow.approve(R);
        vm.expectRevert(FrameBountyEscrow.Unauthorized.selector);
        vm.prank(STRANGER);
        escrow.refund(JOB, REFUND, 1);
        vm.expectRevert(FrameBountyEscrow.Unauthorized.selector);
        vm.prank(STRANGER);
        escrow.close(JOB);
        conservation();
    }

    function testNoOversubscriptionOrRecipientMutationOrDoublePayout() public {
        submitted(20_000_000);
        vm.expectRevert(FrameBountyEscrow.InsufficientFunds.selector);
        vm.prank(ALLOCATOR);
        escrow.reserve(JOB, keccak256("second"), STRANGER, 1, uint64(block.timestamp + 1));
        vm.prank(REVIEWER);
        escrow.approve(R);
        require(token.balanceOf(CONTRIBUTOR) == 20_000_000, "fixed recipient and amount");
        require(token.balanceOf(STRANGER) == 0, "no destination substitution");
        vm.expectRevert(FrameBountyEscrow.InvalidState.selector);
        vm.prank(REVIEWER);
        escrow.approve(R);
        vm.expectRevert(FrameBountyEscrow.InvalidTerms.selector);
        vm.prank(ALLOCATOR);
        escrow.reserve(JOB, R, STRANGER, 1, uint64(block.timestamp + 1));
        conservation();
    }

    function testCloseRefundPreservesSubmittedObligation() public {
        submitted(1_000_000);
        vm.prank(BUYER);
        escrow.close(JOB);
        vm.prank(BUYER);
        escrow.refund(JOB, REFUND, 19_000_000);
        vm.expectRevert(FrameBountyEscrow.InsufficientFunds.selector);
        vm.prank(BUYER);
        escrow.refund(JOB, keccak256("second-refund"), 1);
        vm.warp(block.timestamp + 2 hours);
        vm.expectRevert(FrameBountyEscrow.InvalidState.selector);
        escrow.expire(R); // Original upload expiry no longer releases this obligation.
        vm.prank(REVIEWER);
        escrow.approve(R);
        conservation();
    }

    function testClosedJobStillAcceptsValidReservedSubmission() public {
        reserved(1_000_000);
        vm.prank(BUYER);
        escrow.close(JOB);
        vm.prank(CONTRIBUTOR);
        escrow.submit(R, keccak256("clip"));
        vm.prank(REVIEWER);
        escrow.approve(R);
        conservation();
    }

    function testExpiryBoundaryAndTerminalRelease() public {
        reserved(1_000_000);
        vm.warp(block.timestamp + 1 hours);
        vm.expectRevert(FrameBountyEscrow.InvalidState.selector);
        vm.prank(CONTRIBUTOR);
        escrow.submit(R, keccak256("late"));
        escrow.expire(R);
        vm.expectRevert(FrameBountyEscrow.InvalidState.selector);
        escrow.expire(R);
        require(escrow.available(JOB) == 20_000_000, "expiry released once");
        conservation();
    }

    function testReviewTimeoutBoundaryCannotRaceApproval() public {
        submitted(1_000_000);
        vm.warp(block.timestamp + 72 hours);
        vm.expectRevert(FrameBountyEscrow.InvalidState.selector);
        vm.prank(REVIEWER);
        escrow.approve(R);
        escrow.timeout(R);
        vm.prank(BUYER);
        escrow.close(JOB);
        vm.prank(BUYER);
        escrow.refund(JOB, REFUND, 20_000_000);
        conservation();
    }

    function testRejectionRequiresReasonAndIsTerminal() public {
        submitted(1_000_000);
        vm.expectRevert(FrameBountyEscrow.InvalidTerms.selector);
        vm.prank(REVIEWER);
        escrow.reject(R, bytes32(0));
        vm.prank(REVIEWER);
        escrow.reject(R, keccak256("incomplete fold"));
        vm.expectRevert(FrameBountyEscrow.InvalidState.selector);
        vm.prank(REVIEWER);
        escrow.approve(R);
        conservation();
    }

    function testPayoutFailureKeepsObligation() public {
        submitted(1_000_000);
        token.setFailure(true);
        vm.expectRevert();
        vm.prank(REVIEWER);
        escrow.approve(R);
        require(escrow.available(JOB) == 19_000_000, "failed payment remains committed");
        require(token.balanceOf(CONTRIBUTOR) == 0, "not paid");
        token.setFailure(false);
        vm.prank(REVIEWER);
        escrow.approve(R);
        conservation();
    }

    function testFeeTokenDepositRevertsWithoutCrediting() public {
        bytes32 feeJob = keccak256("fee-token-first-deposit");
        vm.prank(BUYER);
        escrow.createJob(feeJob, REVIEWER, ALLOCATOR, keccak256("rubric"), 1 hours);
        token.mint(BUYER, 1_000_000);
        token.setFee(true);
        vm.expectRevert(FrameBountyEscrow.UnsupportedToken.selector);
        vm.prank(BUYER);
        escrow.deposit(feeJob, 1_000_000);
        conservation();
    }

    function testZeroAndMaximumRewardsFailSafely() public {
        vm.expectRevert(FrameBountyEscrow.InvalidTerms.selector);
        vm.prank(ALLOCATOR);
        escrow.reserve(JOB, R, CONTRIBUTOR, 0, uint64(block.timestamp + 1));
        vm.expectRevert(FrameBountyEscrow.InsufficientFunds.selector);
        vm.prank(ALLOCATOR);
        escrow.reserve(JOB, R, CONTRIBUTOR, type(uint256).max, uint64(block.timestamp + 1));
        conservation();
    }

    function testFuzzRewardConservation(uint96 raw, bool accept) public {
        uint256 reward = uint256(raw) % 20_000_000 + 1;
        submitted(reward);
        vm.prank(BUYER);
        escrow.close(JOB);
        if (accept) {
            vm.prank(REVIEWER);
            escrow.approve(R);
        } else {
            vm.warp(block.timestamp + 72 hours);
            escrow.timeout(R);
        }
        uint256 uncommitted = escrow.available(JOB);
        if (uncommitted != 0) {
            vm.prank(BUYER);
            escrow.refund(JOB, REFUND, uncommitted);
        }
        conservation();
    }

    function testMaliciousTokenCannotReenterPayout() public {
        bytes32 job2 = keccak256("malicious-callback-job");
        bytes32 reservation2 = keccak256("malicious-callback-reservation");
        token.mint(BUYER, 1_000_000);
        vm.prank(BUYER);
        escrow.createJob(job2, address(token), ALLOCATOR, keccak256("rubric"), 1 hours);
        vm.prank(BUYER);
        escrow.deposit(job2, 1_000_000);
        vm.prank(ALLOCATOR);
        escrow.reserve(job2, reservation2, CONTRIBUTOR, 1_000_000, uint64(block.timestamp + 1 hours));
        vm.prank(CONTRIBUTOR);
        escrow.submit(reservation2, keccak256("clip"));
        token.setCallback(address(escrow), abi.encodeCall(escrow.approve, (reservation2)));
        vm.prank(address(token));
        escrow.approve(reservation2);
        require(!token.callbackSucceeded(), "reentrant approval must fail");
        require(token.balanceOf(CONTRIBUTOR) == 1_000_000, "paid exactly once");
    }

    function testJobsCannotSpendEachOthersDeposits() public {
        bytes32 job2 = keccak256("unfunded-job");
        vm.prank(STRANGER);
        escrow.createJob(job2, STRANGER, STRANGER, keccak256("rubric"), 1 hours);
        vm.expectRevert(FrameBountyEscrow.InsufficientFunds.selector);
        vm.prank(STRANGER);
        escrow.reserve(job2, R, STRANGER, 1, uint64(block.timestamp + 1));
        require(escrow.available(JOB) == 20_000_000, "other job's funds untouched");
        conservation();
    }

    function testFundingRetryCannotDebitTheFixedBudgetTwice() public {
        token.mint(BUYER, 20_000_000);
        vm.expectRevert(FrameBountyEscrow.InvalidState.selector);
        vm.prank(BUYER);
        escrow.deposit(JOB, 20_000_000);
        require(token.balanceOf(BUYER) == 20_000_000, "duplicate funding debited buyer");
        require(escrow.available(JOB) == 20_000_000, "budget changed on retry");
        conservation();
    }

    function testRefundRetryCannotSpendNewlyReleasedFunds() public {
        submitted(1_000_000);
        vm.prank(BUYER);
        escrow.close(JOB);
        vm.prank(BUYER);
        escrow.refund(JOB, REFUND, 19_000_000);
        vm.prank(REVIEWER);
        escrow.reject(R, keccak256("incomplete task"));
        vm.expectRevert(FrameBountyEscrow.InvalidTerms.selector);
        vm.prank(BUYER);
        escrow.refund(JOB, REFUND, 1_000_000);
        vm.prank(BUYER);
        escrow.refund(JOB, keccak256("released-obligation-refund"), 1_000_000);
        require(token.balanceOf(BUYER) == 20_000_000, "remaining funds inaccessible");
        conservation();
    }

    function testFuzzOperationSequenceConservesFunds(uint256 seed) public {
        for (uint256 step; step < 32; step++) {
            uint256 random = uint256(keccak256(abi.encode(seed, step)));
            bytes32 id = keccak256(abi.encode("sequence", random % 8));
            uint256 action = (random / 8) % 8;
            bytes memory data;
            address actor;
            if (action == 0) {
                actor = ALLOCATOR;
                data = abi.encodeCall(escrow.reserve, (JOB, id, CONTRIBUTOR, random % 5_000_000 + 1, uint64(block.timestamp + 1 hours)));
            } else if (action == 1) {
                actor = CONTRIBUTOR;
                data = abi.encodeCall(escrow.submit, (id, keccak256("clip")));
            } else if (action == 2) {
                actor = REVIEWER;
                data = abi.encodeCall(escrow.approve, (id));
            } else if (action == 3) {
                actor = REVIEWER;
                data = abi.encodeCall(escrow.reject, (id, keccak256("reason")));
            } else if (action == 4) {
                actor = STRANGER;
                data = abi.encodeCall(escrow.expire, (id));
            } else if (action == 5) {
                actor = STRANGER;
                data = abi.encodeCall(escrow.timeout, (id));
            } else if (action == 6) {
                actor = BUYER;
                data = abi.encodeCall(escrow.close, (JOB));
            } else {
                actor = BUYER;
                data = abi.encodeCall(escrow.refund, (JOB, keccak256(abi.encode("sequence-refund", step)), escrow.available(JOB)));
            }
            if (random % 3 == 0) vm.warp(block.timestamp + 2 hours);
            vm.prank(actor);
            // Invalid orderings may revert. Every prefix, including reverted calls,
            // must conserve funds and remain backed by the real local token balance.
            (bool succeeded,) = address(escrow).call(data);
            if (!succeeded) require(token.balanceOf(STRANGER) == 0, "failed call leaked funds");
            conservation();
        }
    }

    function twoSubmitted() internal returns (bytes32[] memory ids) {
        submitted(1_000_000);
        bytes32 second = keccak256("second-reservation");
        vm.prank(ALLOCATOR);
        escrow.reserve(JOB, second, CONTRIBUTOR, 1_000_000, uint64(block.timestamp + 1 hours));
        vm.prank(CONTRIBUTOR);
        escrow.submit(second, keccak256("second-content"));
        ids = new bytes32[](2); ids[0] = R; ids[1] = second;
    }

    function testBatchPaysFixedRecipientsOnceAndCannotBeSentByAllocator() public {
        bytes32[] memory ids = twoSubmitted();
        vm.expectRevert(); vm.prank(ALLOCATOR); escrow.approveBatch(keccak256("batch"), ids);
        vm.prank(REVIEWER); escrow.approveBatch(keccak256("batch"), ids);
        require(token.balanceOf(CONTRIBUTOR) == 2_000_000, "batch fixed rewards");
        vm.expectRevert(); vm.prank(REVIEWER); escrow.approveBatch(keccak256("batch"), ids);
        conservation();
    }

    function testBatchDuplicateAndFailedTransferAreAtomic() public {
        bytes32[] memory ids = twoSubmitted();
        ids[1] = ids[0];
        vm.expectRevert(); vm.prank(REVIEWER); escrow.approveBatch(keccak256("duplicate"), ids);
        ids[1] = keccak256("second-reservation");
        token.setFailure(true);
        vm.expectRevert(); vm.prank(REVIEWER); escrow.approveBatch(keccak256("failure"), ids);
        require(token.balanceOf(CONTRIBUTOR) == 0, "failed batch paid");
        require(!escrow.paidBatches(keccak256("failure")), "failed batch consumed");
        conservation();
    }

    function testVerifierCanRejectButCannotPay() public {
        submitted(1_000_000);
        vm.expectRevert(); vm.prank(STRANGER); escrow.rejectVerification(R, keccak256("failure"));
        vm.expectRevert(); vm.prank(ALLOCATOR); escrow.approve(R);
        vm.prank(ALLOCATOR); escrow.rejectVerification(R, keccak256("failure"));
        require(token.balanceOf(CONTRIBUTOR) == 0, "rejection paid");
        require(escrow.available(JOB) == 20_000_000, "rejection retained commitment");
        vm.expectRevert(); vm.prank(ALLOCATOR); escrow.rejectVerification(R, keccak256("failure"));
        conservation();
    }
}
