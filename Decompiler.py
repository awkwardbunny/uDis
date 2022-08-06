#!/usr/bin/env python3
import logging
from dataclasses import dataclass, field
from pprint import pprint, pformat
from typing import List, Dict, Any, Union, Set

import coloredlogs

from main import CodeBlock as ParsedCodeBlock

log = logging.getLogger(__name__)
coloredlogs.install(level="DEBUG")


@dataclass
class Bytecode:
    offset: int
    opcode: str
    operands: str
    lineno: Union[int | None]
    attr: Dict[Any, Any] = field(default_factory=dict)

    def line_str(self) -> str:
        return f"   # line {self.lineno}" if self.lineno is not None else ""

    def __str__(self) -> str:
        return f"{self.offset} {self.opcode} {self.operands}{self.line_str()}"


@dataclass
class BasicBlock:
    label: str
    bytecode: Dict[int, Bytecode]

    def add_bytecode(self, b: Bytecode):
        self.bytecode[b.offset] = b


@dataclass
class CodeBlock:
    name: str
    source: str
    args: List[str]
    blocks: List[BasicBlock]
    line_info: Dict[int, int]

    @staticmethod
    def from_parsed_code_block(cb: ParsedCodeBlock) -> "CodeBlock":
        bc: Dict[int, Bytecode] = dict()
        for b in cb.bytecode:
            offset = b[0]
            lineno = cb.line_info[offset] if offset in cb.line_info else None
            bc[offset] = Bytecode(*b, lineno)

        bb: List[BasicBlock] = [BasicBlock("L0", bc)]
        return CodeBlock(cb.name, cb.source_file, cb.args, bb, cb.line_info)


@dataclass
class LineBuffer:
    buf: List[str] = field(default_factory=list)
    logger: logging.Logger = None
    log: bool = False

    def newline(self):
        self.append("")

    def append(self, line: str):
        self.buf.append(line)
        if self.log:
            self.logger.warning(f"OUT: {line}")

    def dump(self) -> str:
        return '\n'.join(self.buf)


class uDecompiler:
    top_desc: str
    blocks: Dict[str, CodeBlock] = dict()

    def __init__(self, blocks_in: Dict[str, ParsedCodeBlock], top_cb_name: str = "<module>"):
        log.info("Initializing decompiler...")
        log.info("* Performing initial conversion to basic blocks...")
        self.blocks = dict(map(lambda b: (b[0], CodeBlock.from_parsed_code_block(b[1])), blocks_in.items()))

        for desc, block in self.blocks.items():
            if block.name == top_cb_name:
                self.top_desc = desc
                break
        log.info(f"* Top block '{top_cb_name}' found ({self.top_desc})")

    def decompile(self, start_name: str = "<module>") -> str:
        log.info("Running decompilation...")
        # log.debug(pformat(self.blocks))

        log.info("* Pass 0: Break down basic blocks")
        self.pass_0()

        # for now
        output = self.disassemble()
        # log.debug(output)
        return output

    def pass_0(self):
        for codeblock in self.blocks.values():
            # log.debug(f"** PASS_0 :: {codeblock.name}")
            block_0 = codeblock.blocks[0]  # There should only be one at this point

            jmp_targets: Set[int] = set()
            for bc in block_0.bytecode.values():
                # log.debug(f"** Processing :: {bc}")
                if bc.opcode == "UNWIND_JUMP":
                    targets = bc.operands.split()
                    jmp_targets.add(int(targets[0]))
                    jmp_targets.add(int(targets[1]))
                elif "JUMP" in bc.opcode:
                    target = int(bc.operands)
                    # log.warning(f"Found jump: {bc.offset} -> {target}")
                    jmp_targets.add(target)
            jmp_targets: List[int] = sorted(jmp_targets)
            if len(jmp_targets) == 0:
                # log.debug("No jump targets; skipping")
                continue

            jmp_targets.insert(0, 0)
            # log.debug(f"JUMP_TARGETS: {jmp_targets}")
            jmp_targets.append(9999)

            blocks: List[BasicBlock] = list()
            bytecodes: Dict[int, Bytecode] = dict()
            i = 0
            for offset, bc in block_0.bytecode.items():
                if i == len(jmp_targets) - 1:
                    blocks.append(BasicBlock(f"L{jmp_targets[i-1]}", bytecodes))
                    break

                start = jmp_targets[i]
                stop = jmp_targets[i+1]
                if start <= offset < stop:
                    bytecodes[offset] = bc
                else:
                    blocks.append(BasicBlock(f"L{start}", bytecodes))
                    bytecodes = dict()
                    bytecodes[offset] = bc
                    i += 1
            codeblock.blocks = blocks

    def disassemble(self) -> str:
        buf = LineBuffer([], log, False)
        for block in self.blocks.values():
            buf.append(f"## Source: {block.source}")
            buf.append(f"## Name:   {block.name}")
            buf.append(f"## Args:   {block.args}")
            for bb in block.blocks:
                buf.append(f"{bb.label}:")
                for bc in bb.bytecode.values():
                    buf.append(f"  {bc.opcode} {bc.operands}{bc.line_str()}")
            buf.newline()
        return buf.dump()


def main(args: List[str] = None):
    import argparse
    parser = argparse.ArgumentParser(description='The actual decompiler')
    parser.add_argument('input', type=str, help='Path the the disassembly file generated by the disassembler')
    args = parser.parse_args(args)

    print("Error: Cannot run this program directly (yet)")
    # dec = uDecompiler(args.input)
    # dec.decompile()


if __name__ == "__main__":
    main()
