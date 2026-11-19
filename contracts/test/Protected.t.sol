// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {TestUSDC, Vm} from "./Escrow.t.sol";
import {FrameBountyEscrow} from "../src/FrameBountyEscrow.sol";

contract ProtectedTest {
    Vm constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));
    TestUSDC token;
    FrameBountyEscrow escrow;
    address constant BUYER = address(0xB);
    address constant ORACLE = address(0xC);
    address constant WORKER = address(0xD);
    bytes32 constant JOB = keccak256("protected");
    bytes32 constant RID = keccak256("submission");
    uint64 expiry;

    function setUp() public {
        token = new TestUSDC(); escrow = new FrameBountyEscrow(address(token));
        token.mint(BUYER, 10_000_000);
        expiry = uint64(block.timestamp + 1 days);
        vm.prank(BUYER); token.approve(address(escrow), 10_000_000);
        vm.prank(BUYER); escrow.createProtectedJob(JOB, BUYER, ORACLE, keccak256("terms"), 1 hours, expiry, 900);
        vm.prank(BUYER); escrow.deposit(JOB, 10_000_000);
    }
    function submit() internal {
        vm.prank(ORACLE); escrow.reserve(JOB, RID, WORKER, 1_000_000, uint64(block.timestamp + 1800));
        vm.prank(WORKER); escrow.submit(RID, keccak256("original"));
    }
    function verify() internal {
        submit(); vm.prank(ORACLE); escrow.verify(RID, keccak256("evidence"));
    }
    function testBudgetCannotCloseOrRefundEarly() public {
        vm.expectRevert(); vm.prank(BUYER); escrow.close(JOB);
        vm.expectRevert(); vm.prank(BUYER); escrow.refund(JOB, keccak256("refund"), 1);
        vm.warp(expiry); vm.prank(BUYER); escrow.close(JOB);
        vm.prank(BUYER); escrow.refund(JOB, keccak256("refund"), 10_000_000);
        require(token.balanceOf(BUYER) == 10_000_000);
    }
    function testReservationCannotExceedTwiceEstimateOrBeSelfTrade() public {
        vm.expectRevert(); vm.prank(ORACLE); escrow.reserve(JOB, RID, WORKER, 1, uint64(block.timestamp + 1801));
        vm.expectRevert(); vm.prank(ORACLE); escrow.reserve(JOB, RID, BUYER, 1, uint64(block.timestamp + 900));
        vm.expectRevert(); vm.prank(BUYER); escrow.reserve(JOB, RID, WORKER, 1, uint64(block.timestamp + 900));
    }
    function testBuyerCannotRejectOrPayUnverified() public {
        submit();
        vm.expectRevert(); vm.prank(BUYER); escrow.approve(RID);
        vm.expectRevert(); vm.prank(BUYER); escrow.reject(RID, keccak256("veto"));
        vm.expectRevert(); escrow.settle(RID);
        vm.warp(block.timestamp + 2 days);
        vm.expectRevert(); escrow.timeout(RID);
        vm.prank(ORACLE); escrow.verify(RID, keccak256("late-provider-recovery"));
    }
    function testPermissionlessPaymentAtExactDeadlineAndNoDoublePay() public {
        verify(); uint64 due = escrow.payAfter(RID);
        vm.warp(due - 1); vm.expectRevert(); escrow.settle(RID);
        vm.warp(due); escrow.settle(RID);
        require(token.balanceOf(WORKER) == 1_000_000);
        vm.expectRevert(); escrow.settle(RID);
    }
    function testVerifiedObligationSurvivesPostExpiryRefundAndOracleRejection() public {
        verify();
        vm.expectRevert(); vm.prank(ORACLE); escrow.rejectVerification(RID, keccak256("changed-mind"));
        vm.expectRevert(); vm.prank(ORACLE); escrow.verify(RID, keccak256("restart-timer"));
        vm.warp(expiry); vm.prank(BUYER); escrow.close(JOB);
        vm.prank(BUYER); escrow.refund(JOB, keccak256("unused"), 9_000_000);
        escrow.settle(RID); require(token.balanceOf(WORKER) == 1_000_000);
    }
    function testImmediateBatchAndCounterpartyRatings() public {
        verify(); bytes32[] memory ids = new bytes32[](1); ids[0] = RID;
        vm.prank(BUYER); escrow.approveBatch(keccak256("batch"), ids);
        vm.prank(WORKER); escrow.rate(RID, 1);
        vm.prank(BUYER); escrow.rate(RID, -1);
        (uint256 up, uint256 down) = escrow.buyerScores(BUYER); require(up == 1 && down == 0);
        (up, down) = escrow.contributorScores(WORKER); require(up == 0 && down == 1);
        vm.expectRevert(); vm.prank(WORKER); escrow.rate(RID, -1);
        vm.expectRevert(); escrow.rate(RID, 1);
    }
    function testNoRatingBeforePaidOrInvalidVote() public {
        submit(); vm.expectRevert(); vm.prank(WORKER); escrow.rate(RID, 1);
        vm.prank(ORACLE); escrow.verify(RID, keccak256("evidence"));
        vm.prank(BUYER); escrow.approve(RID);
        vm.expectRevert(); vm.prank(WORKER); escrow.rate(RID, 0);
    }
    function testTransferFailureDoesNotConsumeAutomaticPayment() public {
        verify(); vm.warp(escrow.payAfter(RID)); token.setFailure(true);
        vm.expectRevert(); escrow.settle(RID);
        token.setFailure(false); escrow.settle(RID);
        require(token.balanceOf(WORKER) == 1_000_000);
    }
}

