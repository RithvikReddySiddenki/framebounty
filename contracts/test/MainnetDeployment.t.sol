// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {FrameBountyEscrow} from "../src/FrameBountyEscrow.sol";
import {TestUSDC} from "./Escrow.t.sol";

interface VmNetwork {
    function chainId(uint256) external;
    function etch(address, bytes calldata) external;
    function expectRevert(bytes4) external;
}

contract MainnetDeploymentTest {
    VmNetwork constant vm = VmNetwork(address(uint160(uint256(keccak256("hevm cheat code")))));
    address constant USDC = 0x3600000000000000000000000000000000000000;

    function testMainnetConstructorAcceptsOnlyCanonicalSixDecimalUsdc() public {
        TestUSDC source = new TestUSDC();
        vm.etch(USDC, address(source).code);
        vm.chainId(5042);
        FrameBountyEscrow escrow = new FrameBountyEscrow(USDC);
        require(address(escrow.token()) == USDC);
        vm.expectRevert(FrameBountyEscrow.UnsupportedToken.selector);
        new FrameBountyEscrow(address(source));
    }

    function testMainnetSupportDoesNotEnableOtherChains() public {
        TestUSDC source = new TestUSDC();
        vm.chainId(1);
        vm.expectRevert(FrameBountyEscrow.InvalidTerms.selector);
        new FrameBountyEscrow(address(source));
    }
}
