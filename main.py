#!/usr/bin/env python3
import argparse
import datetime
import logging
import os
import subprocess
import traceback
from dataclasses import dataclass
from typing import List, Dict, Any, Callable, Tuple
from pprint import pprint

import coloredlogs

log = logging.getLogger(__name__)
coloredlogs.install(level="DEBUG")


def get_git_version() -> str:
    status = subprocess.run("git describe --always".split(), capture_output=True)
    return status.stdout.decode().strip()


VERSION = get_git_version()


@dataclass
class CodeBlock:
    name: str
    source_file: str
    descriptor: str
    args: List[str]
    bytecode: List[Tuple[int, str, str]]
    line_info: Dict[int, int]

    def set_args(self, args: List[str]):
        self.args = args

    def add_bytecode(self, b: Tuple[int, str, str]):
        self.bytecode.append(b)

    def add_line_info(self, bc: int, line: int):
        self.line_info[bc] = line


def disassemble(filename: str) -> Dict[str, CodeBlock]:
    module_name = filename[:-4]
    log.info(f"Disassembling '{module_name}'...")

    # Get disassembly
    status = subprocess.run(f"./micropython/micropython -v -v -v -v -m {module_name}".split(), capture_output=True)
    output = status.stdout.decode().split("\n")

    " Errors can usually be ignored since we are not actually trying to run the files "
    " Uncomment for debug "
    # for e in status.stderr.decode().split("\n"):
    #     log.debug(e)

    code_blocks: Dict[str, CodeBlock] = dict()
    current_block: CodeBlock = None
    for line in output:
        if line.startswith("mem"):
            break  # end of disassmbly

        if len(line.strip()) == 0:
            continue
        if line[0] == '(' or line.startswith("Raw bytecode"):
            continue

        if line.startswith("  "):
            parts = line.strip().split()
            bc = int(parts[0].split('=')[1])
            line = int(parts[1].split('=')[1])
            current_block.add_line_info(bc, line)
            continue

        if line[0] == ' ':
            continue

        line = line.strip()
        if line.startswith("File"):
            if current_block is not None:
                code_blocks[current_block.descriptor] = current_block

            source_name = line[5:].split(',')[0]
            block_name = line.split("'")[1]
            block_desc = line.split()[6][:-1]
            current_block = CodeBlock(block_name, source_name, block_desc, [], [], {})
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
            last = current_block.bytecode[-1]
            offset, op, args = last
            args += "\n" + line
            current_block.bytecode[-1] = (offset, op, args)
            continue

        instr = parts[1]
        operands = ' '.join(parts[2:])
        current_block.add_bytecode((num, instr, operands))
    if current_block is not None:
        code_blocks[current_block.descriptor] = current_block
    return code_blocks


def write_dis_to_file(cb: Dict[str, CodeBlock], filepath: str):
    log.info(f"Writing disassembly to '{filepath}'")
    with open(filepath, 'w') as out_f:
        for b in cb.values():
            out_f.write(f"# def {b.name}({','.join(b.args)}) #{b.descriptor}\n")
            out_f.write(f"{b.name}:\n")
            for bc in b.bytecode:
                out_f.write(f"  {bc[1]} {bc[2]}\n")
            out_f.write("\n")


class Buffer:
    buf: List[str] = list()

    def newline(self):
        self.buf.append("")

    def append(self, s: str):
        log.error(f"::EMIT {s}")
        self.buf.append(s)


class Stack:
    buf: List[Any] = list()

    def push(self, v: Any):
        self.buf.insert(0, v)

    def pop(self) -> Any:
        return self.buf.pop(0)

    def dump(self) -> str:
        return f"{self.buf}"

    def peek(self, i: int = 0) -> Any:
        return self.buf[i]


def decompile(module_name: str, dis: Dict[str, CodeBlock], fn_dec: str):
    log.info(f"Decompiling '{module_name}'...")
    timestamp = datetime.datetime.now()

    from Decompiler import uDecompiler
    dec = uDecompiler(dis)
    buf = dec.decompile()

    with open(fn_dec, 'w') as out_f:
        out_f.write(f"####################################\n")
        out_f.write(f"## Decompiled with uDis ({VERSION}) ##\n")
        out_f.write(f"## At: {timestamp} ##\n")
        out_f.write(f"####################################\n\n")
        out_f.write(buf)
        out_f.write("\n")


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

        dis = disassemble(fn_mpy)
        write_dis_to_file(dis, fn_asm)
        decompile(module_name, dis, fn_dec)
    log.info("Done.")


if __name__ == "__main__":
    main()
