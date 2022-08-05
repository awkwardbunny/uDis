# µDis
MicroPython Decompiler

Currently uses v1.18 release of [MicroPython](https://github.com/micropython/micropython), which uses bytecode version 5 ([doc](http://docs.micropython.org/en/latest/reference/mpyfiles.html#versioning-and-compatibility-of-mpy-files))

The bytecode is generated from MicroPython itself. The `micropython/micropython` binary is the built Unix port of the MicroPython interpreter. Docs on building it can be found [here](https://docs.micropython.org/en/latest/develop/gettingstarted.html#building-the-unix-port-of-micropython)

Bytecode version 6 for MicroPython v1.19+ should be fairly easy to support by replacing `micropython/micropython` binary (and maybe minor modifications to `main.py`).

Disassembly works.
Decompile not working yet.

## Understanding the Python Bytecode
The program will output the disassembled bytecode and decompiled source.
As decompilation isn't working, all we have is the disassembly.

You probably want to start with the `<module>` code block and follow the code instructions (defining functions, classes, methods).
If the compiled program isn't super complex, you can recreate the original Python source pretty closely.
Well, probably close enough.

The reference for all the bytecode instructions can be found on `dis` package's [docs](https://docs.python.org/3/library/dis.html#python-bytecode-instructions), although I think there are some differences. See the section below.

## Differences from regular Python (CPython)
MicroPython's docs has a whole [section](http://docs.micropython.org/en/latest/genrst/index.html) on this, so take a look at that, but I don't think it mentions anything on the bytecode level.

### MAKE\_FUNCTION
I think `MAKE_FUNCTION` works differently? The docs from `dis` package [link](https://docs.python.org/3/library/dis.html#opcode-MAKE_FUNCTION) explains that this opcode takes 2 or more values from the stack (function name and associated code), but in disassembly, you get something like:
```
  16 LOAD_BUILD_CLASS
  17 MAKE_FUNCTION 7f3b31b56b00
```
where `7f3b31b56b00` is the descriptor given by the micropython binary. The inner code blocks are defined first, and the outer ones are defined with references to them, which is why I think it makes sense that the module-level code block (labelled `<module>`) is shown at the end.

Update: Actually, recalling from looking at the mpy binary format, the code blocks (MicroPython calls them "RawCode" structures) were nested insides another resembling a module how you would imagine it to be structured in memory/file. So the inner code blocks are not defined/parsed before the outer blocks. There's probably something I'm missing.

Update 2: Was thinking about it a bit more. The dump/freeze files that the [`mpy-tool.py`](https://github.com/micropython/micropython/blob/v1.18/tools/mpy-tool.py) outputs has `MAKE_FUNCTION 0`. Whereas CPython needs two arguments on the stack (name and code), MicroPython might just be referencing one of its children code blocks by index, since every code block already has name and code stored in it.

## Running from source
Requires Python 3.10 or higher for 'match' ([PEP 636](https://peps.python.org/pep-0636/)).
Consider using the [docker method](#running-with-docker) below.

```bash
$ git clone https://github.com/awkwardbunny/uDis.git
$ cd uDis
$ pip3 install -r requirements.txt
$ cp <compiled mpy files> in/   # Place mpy files inside 'in/' directory
$ ls in/
hello_world.mpy test.mpy
$ ./main.py in out
$ ls out/
hello_world.py hello_world.s test.py test.s
```

## Running with Docker
Alternatively, if setting up Python 3.10+ is an issue, Docker can be used.

```bash
$ docker run -it -rm -v <path containing mpy files>:/code/in -v <output dir>:/code/out ghcr.io/awkwardbunny/udis:main
```
