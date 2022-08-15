#!/usr/bin/env python3
import argparse
import datetime
import logging
import os
import subprocess
import traceback
from dataclasses import dataclass, field
from typing import List, Dict, Any, Callable, Tuple, Union, Iterator
from pprint import pprint

from lark import Lark
from lark.lexer import Lexer, Token
import coloredlogs

log = logging.getLogger(__name__)
coloredlogs.install(level="DEBUG")


def get_git_version() -> str:
    status = subprocess.run("git describe --always".split(), capture_output=True)
    return status.stdout.decode().strip()


VERSION = get_git_version()


def getGrammar(fn: str) -> str:
    with open(fn, 'r') as f:
        return f.read()


@dataclass
class Bytecode:
    offset: int
    opcode: str
    operands: str
    lineno: Union[int | None]
    attr: Dict[Any, Any] = field(default_factory=dict)

    def get_opcode(self) -> str:
        return self.opcode

    def line_str(self) -> str:
        return f"   # line {self.lineno}" if self.lineno is not None else ""

    def __str__(self) -> str:
        return f"{self.offset} {self.opcode} {self.operands}{self.line_str()}"


@dataclass
class CodeBlock:
    name: str
    source: str
    desc: str
    args: List[str]
    code: Dict[int, Bytecode]

    def set_args(self, args: List[str]):
        self.args = args

    def add_bytecode(self, b: Bytecode):
        self.code[b.offset] = b


class Buffer:
    buf: List[str]

    def __init__(self):
        self.buf = []

    def print(self, s: str = ""):
        self.write(s+"\n")

    def write(self, s: str, print: bool = False):
        if print:
            log.error(f"::EMIT {s}")
        self.buf.append(s)

    def dump(self) -> str:
        return ''.join(self.buf)


class uDisLexer(Lexer):
    def __init__(self, _lexer_conf):
        pass

    def lex(self, data) -> Iterator[Token]:
        for block in data.blocks.values():
            yield Token("METADATA", (block.source, block.name, block.args))
            for bc in block.code.values():
                yield Token(bc.opcode, (bc.offset, bc.operands))

class uDecompiler:
    filename: str
    module_name: str
    parser: Lark

    tab: str = " " * 4
    blocks: Dict[str, CodeBlock] = None

    def __init__(self, mpy_fn: str, module_name: str, grammar_file: str = "upython.grammar"):
        self.filename = mpy_fn
        self.module_name = module_name
        self.parser = Lark(getGrammar(grammar_file), parser="lalr", lexer=uDisLexer)

    def disassemble(self):
        log.info("Disassembling")

        # Get disassembly
        status = subprocess.run(f"./micropython/micropython -v -v -v -v -m {self.filename}".split(), capture_output=True)
        output = status.stdout.decode().split("\n")

        " Errors can usually be ignored since we are not actually trying to run the files "
        " Uncomment for debug "
        # for e in status.stderr.decode().split("\n"):
        #     log.debug(e)

        self.blocks: Dict[str, CodeBlock] = {}
        lineinfo: Dict[int, int] = {}

        current_block: CodeBlock = None
        for line in output:
            if line.startswith("mem"):
                break  # end of disassmbly
            if len(line.strip()) == 0:
                continue
            if line[0] == '(' or line.startswith("Raw bytecode"):
                continue

            # Source line information
            if line.startswith("  "):
                parts = line.strip().split()
                bc = int(parts[0].split('=')[1])  # bc=x
                line = int(parts[1].split('=')[1])  # line=x
                lineinfo[bc] = line
                continue

            if line[0] == ' ':
                continue

            line = line.strip()
            if line.startswith("File"):
                if current_block is not None:
                    self.blocks[current_block.desc] = current_block

                source_name = line[5:].split(',')[0]
                block_name = line.split("'")[1]
                block_desc = line.split()[6][:-1]
                current_block = CodeBlock(block_name, source_name, block_desc, [], {})
                log.info(f"* Code block '{block_name}' ({block_desc})")
                continue

            if line.startswith("arg names:"):
                args = line.split()[2:]
                current_block.set_args(args)
                continue

            parts = line.split()

            # HACKY: handle edge case where a newline inside const was printed
            try:
                num = int(parts[0])
            except ValueError:
                last = current_block.code[-1]
                last.operands += "\n" + line
                continue

            instr = parts[1]
            operands = ' '.join(parts[2:])
            lineno = lineinfo[num] if num in lineinfo.keys() else None
            current_block.add_bytecode(Bytecode(num, instr, operands, lineno))
        if current_block is not None:
            self.blocks[current_block.desc] = current_block

    def get_disassembly(self) -> str:
        if self.blocks is None:
            self.disassemble()

        timestamp = datetime.datetime.now()

        buf = Buffer()
        buf.print(f"######################################")
        buf.print(f"## Disassembled with uDis ({VERSION}) ##")
        buf.print(f"## At: {timestamp}   ##")
        buf.print(f"######################################\n")

        for block in self.blocks.values():
            buf.print(f"## Source: {block.source}")
            buf.print(f"## Name:   {block.name}")
            buf.print(f"## Args:   {block.args}")

            for bc in block.code.values():
                if bc.lineno is not None:
                    buf.print()
                if bc.opcode == "MAKE_FUNCTION":
                    func_name = self.blocks[bc.operands].name
                    buf.print(f"{bc.opcode} {bc.operands}({func_name}){bc.line_str()}")
                else:
                    buf.print(f"{bc.opcode} {bc.operands}{bc.line_str()}")
            buf.print()
        buf.print()
        return buf.dump()

    def decompile(self) -> str:
        if self.blocks is None:
            self.disassemble()

        log.info("Decompiling")
        timestamp = datetime.datetime.now()

        buf = Buffer()
        buf.print(f"####################################")
        buf.print(f"## Decompiled with uDis ({VERSION}) ##")
        buf.print(f"## At: {timestamp} ##")
        buf.print(f"####################################\n")

        # TODO
        l = uDisLexer(None)
        for x in l.lex(self):
            log.debug(f"{x.type}: {x.value}")
        # self.parser.parse(self)

        buf.print()
        return buf.dump()


def main(args: List[str] = None):
    log.info(f" *** uDis MicroPython Decompiler ({VERSION}) *** ")
    parser = argparse.ArgumentParser(description='Decompile MicroPython modules')
    parser.add_argument('input_dir', type=str, help='Input directory containing mpy files')
    parser.add_argument('output_dir', type=str, help='Output directory')
    args = parser.parse_args(args)

    for in_f in os.listdir(os.fsencode(args.input_dir)):
        fn = os.fsdecode(in_f)
        if fn[-4:] != ".mpy":
            continue

        module_name = f"{fn[:-4]}"
        fn_mpy = f"{args.input_dir}/{fn}"
        fn_asm = f"{args.output_dir}/{module_name}.s"
        fn_dec = f"{args.output_dir}/{module_name}.py"

        d = uDecompiler(fn_mpy, module_name)
        dis = d.get_disassembly()
        with open(fn_asm, 'w') as f_asm:
            f_asm.write(dis)

        dec = d.decompile()
        with open(fn_dec, 'w') as f_dec:
            f_dec.write(dec)
    log.info("Done.")


if __name__ == "__main__":
    main()
